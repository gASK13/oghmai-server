"""Offline, non-Bedrock migration from legacy word keys to language-qualified keys."""

import argparse
import json
import sys
import unicodedata

import boto3
from botocore.exceptions import ClientError


SUPPORTED_LANGUAGES = {"IT", "DE", "EL"}


def build_word_key(lang, word):
    if not isinstance(lang, str) or lang.strip().upper() not in SUPPORTED_LANGUAGES:
        raise ValueError("lang must be one of IT, DE, EL")
    if not isinstance(word, str) or not word.strip():
        raise ValueError("word must be a non-empty string")
    normalized_word = unicodedata.normalize("NFC", word).strip().casefold()
    return f"{lang.strip().upper()}#{normalized_word}"


def scan_all(table):
    items = []
    start_key = None
    while True:
        kwargs = {"ConsistentRead": True}
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        start_key = response.get("LastEvaluatedKey")
        if not start_key:
            return items


def expected_items(source_items, table_label, report):
    mapped = {}
    for item in source_items:
        try:
            if not item.get("user_id"):
                raise ValueError("user_id must be present")
            key = build_word_key(item.get("lang"), item.get("word"))
            expected = dict(item)
            expected["lang"] = item["lang"].strip().upper()
            expected["word_key"] = key
            identity = (expected["user_id"], key)
            if identity in mapped:
                report[table_label]["invalid_records"].append({
                    "user_id": expected["user_id"], "word_key": key,
                    "reason": "multiple source records normalize to the same destination key",
                })
                continue
            mapped[identity] = expected
        except (ValueError, TypeError) as exc:
            report[table_label]["invalid_records"].append({
                "user_id": item.get("user_id"), "word": item.get("word"), "reason": str(exc),
            })
    return mapped


def canonical(item):
    return json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)


def compare_destinations(table, expected, label, report, allow_missing=False):
    actual_items = scan_all(table)
    actual = {}
    for item in actual_items:
        identity = (item.get("user_id"), item.get("word_key"))
        if identity in actual:
            report[label]["mismatches"].append({"identity": list(identity), "reason": "duplicate destination identity"})
        actual[identity] = item
    report[label]["destination_count"] = len(actual_items)
    for identity, expected_item in expected.items():
        actual_item = actual.get(identity)
        if actual_item is None:
            if not allow_missing:
                report[label]["mismatches"].append({"identity": list(identity), "reason": "missing destination item"})
        elif canonical(actual_item) != canonical(expected_item):
            report[label]["mismatches"].append({"identity": list(identity), "reason": "destination attributes differ from source"})
    for identity in actual.keys() - expected.keys():
        report[label]["mismatches"].append({"identity": list(identity), "reason": "unexpected destination item"})


def migrate_table(source, destination, label, mode, report):
    source_items = scan_all(source)
    report[label]["source_count"] = len(source_items)
    expected = expected_items(source_items, label, report)

    if mode == "execute":
        for identity, item in expected.items():
            response = destination.get_item(
                Key={"user_id": identity[0], "word_key": identity[1]}, ConsistentRead=True
            )
            current = response.get("Item")
            if current is not None:
                if canonical(current) == canonical(item):
                    report[label]["already_present"] += 1
                else:
                    report[label]["mismatches"].append({"identity": list(identity), "reason": "destination key already has different attributes"})
                continue
            try:
                destination.put_item(
                    Item=item,
                    ConditionExpression="attribute_not_exists(user_id) AND attribute_not_exists(word_key)",
                )
                report[label]["written"] += 1
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                    report[label]["errors"].append({"identity": list(identity), "reason": str(exc)})
                    continue
                current = destination.get_item(
                    Key={"user_id": identity[0], "word_key": identity[1]}, ConsistentRead=True
                ).get("Item")
                if current is not None and canonical(current) == canonical(item):
                    report[label]["already_present"] += 1
                else:
                    report[label]["mismatches"].append({"identity": list(identity), "reason": "conditional write raced with conflicting item"})
    elif mode == "dry-run":
        for identity, item in expected.items():
            current = destination.get_item(
                Key={"user_id": identity[0], "word_key": identity[1]}, ConsistentRead=True
            ).get("Item")
            if current is None:
                report[label]["would_write"] += 1
            elif canonical(current) == canonical(item):
                report[label]["already_present"] += 1
            else:
                report[label]["mismatches"].append({"identity": list(identity), "reason": "destination key already has different attributes"})

    compare_destinations(destination, expected, label, report, allow_missing=(mode == "dry-run"))
    report[label]["expected_count"] = len(expected)


def make_report():
    return {
        "mode": None,
        "tables": {
            label: {"source_count": 0, "expected_count": 0, "destination_count": 0,
                    "written": 0, "already_present": 0, "would_write": 0,
                    "invalid_records": [], "mismatches": [], "errors": []}
            for label in ("vocabulary", "recycle_bin")
        },
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true", help="Read and report planned writes without changing destinations")
    modes.add_argument("--execute", action="store_true", help="Copy source records with conditional, idempotent writes")
    modes.add_argument("--verify-only", action="store_true", help="Compare both source tables with destination tables without writing")
    parser.add_argument("--region", required=True, help="AWS region containing all four tables")
    parser.add_argument("--source-vocabulary-table", required=True)
    parser.add_argument("--destination-vocabulary-table", required=True)
    parser.add_argument("--source-recycle-bin-table", required=True)
    parser.add_argument("--destination-recycle-bin-table", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    mode = "execute" if args.execute else "verify-only" if args.verify_only else "dry-run"
    report = make_report()
    report["mode"] = mode
    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    try:
        migrate_table(dynamodb.Table(args.source_vocabulary_table), dynamodb.Table(args.destination_vocabulary_table),
                      "vocabulary", mode, report)
        migrate_table(dynamodb.Table(args.source_recycle_bin_table), dynamodb.Table(args.destination_recycle_bin_table),
                      "recycle_bin", mode, report)
    except Exception as exc:
        report["fatal_error"] = str(exc)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    failed = "fatal_error" in report or any(
        table["invalid_records"] or table["mismatches"] or table["errors"]
        for table in report["tables"].values()
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
