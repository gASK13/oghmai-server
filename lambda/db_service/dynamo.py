import os
import time
import unicodedata
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from fastapi import HTTPException

from models import *
from utils import logging


dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
vocabulary_table_name = os.getenv("VOCABULARY_TABLE", "oghmai_vocabulary_words_v2")
vocabulary_table = dynamodb.Table(vocabulary_table_name)
recycle_bin_table_name = os.getenv("TRASH_BIN_TABLE", "oghmai_vocabulary_recycle_bin_v2")
recycle_bin_table = dynamodb.Table(recycle_bin_table_name)
challenge_table_name = os.getenv("CHALLENGE_TABLE", "oghmai_challenges")
challenge_table = dynamodb.Table(challenge_table_name)


def word_key(lang: str, word: str) -> str:
    """Build the stable DynamoDB sort key used by vocabulary and recycle items."""
    normalized_lang = lang.strip().upper()
    normalized_word = unicodedata.normalize("NFC", word).strip().casefold()
    if not normalized_lang or not normalized_word:
        raise ValueError("Language and word must be non-empty")
    return f"{normalized_lang}#{normalized_word}"


def _query_all(table, **query_args):
    """Return every result page for a DynamoDB Query operation."""
    items = []
    last_evaluated_key = None
    while True:
        if last_evaluated_key:
            query_args["ExclusiveStartKey"] = last_evaluated_key
        response = table.query(**query_args)
        items.extend(response.get("Items", []))
        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            return items


def _get_item(table, user_id: str, lang: str, word: str):
    response = table.get_item(Key={"user_id": user_id, "word_key": word_key(lang, word)})
    return response.get("Item")


def get_words(user_id: str, lang: str, status: str = None, failed_last_test: bool = False, contains: str = None):
    logging.info(f"Filtering words for user {user_id} @ {lang} with status={status}, failed_last_test={failed_last_test}, contains={contains}")
    try:
        filter_expression = None
        if status:
            try:
                status_values = [value.strip() for value in status.split(",")]
                for value in status_values:
                    StatusEnum(value)
                status_filter = (Attr("status").eq(status_values[0]) if len(status_values) == 1
                                 else Attr("status").is_in(status_values))
                filter_expression = status_filter
            except ValueError as exc:
                logging.warning(f"Invalid status value in filter: {str(exc)}")
                raise HTTPException(status_code=400, detail=f"Invalid status value: {str(exc)}")

        query_args = {
            "KeyConditionExpression": Key("user_id").eq(user_id)
            & Key("word_key").begins_with(f"{lang.strip().upper()}#")
        }
        if filter_expression is not None:
            query_args["FilterExpression"] = filter_expression
        items = _query_all(vocabulary_table, **query_args)

        if contains:
            items = [item for item in items if contains.casefold() in item["word"].casefold()]
        word_results = [convert_to_result(item) for item in items]
        if failed_last_test:
            word_results = [result for result in word_results if result.testResults and result.testResults[-1] is False]
        logging.info(f"Retrieved {len(word_results)} filtered words for user {user_id} @ {lang}")
        return [convert_result_to_item(word) for word in word_results]
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logging.error(f"Error filtering words for user {user_id} @ {lang}: {str(exc)}")
        raise HTTPException(status_code=500, detail="Error filtering words")


def get_word(user_id: str, lang: str, word: str):
    logging.info(f"Getting word details {user_id} @ {lang} - {word}")
    try:
        item = _get_item(vocabulary_table, user_id, lang, word)
        if not item:
            logging.info(f"Word {word} not found")
            return None
        return convert_to_result(item)
    except Exception as exc:
        logging.error(f"Error retrieving word: {str(exc)}")
        raise HTTPException(status_code=500, detail="Error retrieving word")


def convert_to_result(item):
    # Keep DynamoDB-only key fields out of the public response model.
    item.pop("word_key", None)
    item["language"] = item.pop("lang", item.get("language", "IT"))
    item["createdAt"] = datetime.fromtimestamp(int(item.pop("created_at", None)), tz=timezone.utc)
    item["lastTest"] = datetime.fromtimestamp(int(item.pop("last_test")), tz=timezone.utc) if item.get("last_test") else None
    item["testResults"] = item.pop("test_results", None)
    return WordResult(**item)


def convert_result_to_item(item: WordResult):
    return WordItem(word=item.word, status=item.status, testResults=item.testResults)


def delete_word(user_id: str, lang: str, word: str):
    logging.info(f"Deleting word {user_id} @ {lang} - {word}")
    key = {"user_id": user_id, "word_key": word_key(lang, word)}
    try:
        response = vocabulary_table.get_item(Key=key)
        item = response.get("Item")
        if not item:
            logging.warning(f"Word {word} not found for deletion")
            raise HTTPException(status_code=404, detail="Word not found")
        item["ttl"] = int(time.time()) + 3600
        recycle_bin_table.put_item(Item=item)
        vocabulary_table.delete_item(Key=key, ConditionExpression=Attr("lang").eq(lang))
        return {"status": "ok", "message": f"Word '{word}' deleted for user '{user_id}'"}
    except HTTPException:
        raise
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logging.warning(f"Conditional check failed when deleting word {exc.response['Error']['Code']}")
            raise HTTPException(status_code=404, detail="Word not found.")
        logging.error(f"Error deleting word: {str(exc)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


def undelete_word(user_id: str, lang: str, word: str):
    logging.info(f"Undeleting word {user_id} @ {lang} - {word}")
    key = {"user_id": user_id, "word_key": word_key(lang, word)}
    try:
        response = recycle_bin_table.get_item(Key=key)
        item = response.get("Item")
        if not item:
            logging.warning(f"Word {word} not found in recycle bin")
            raise HTTPException(status_code=404, detail="Word not found in recycle bin")
        if vocabulary_table.get_item(Key=key).get("Item"):
            logging.warning("Word already exists in main table")
            raise HTTPException(status_code=409, detail="Word already exists in the main table")
        item.pop("ttl", None)
        vocabulary_table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(user_id) AND attribute_not_exists(word_key)",
        )
        recycle_bin_table.delete_item(Key=key)
        return {"status": "ok", "message": f"Word '{word}' restored for user '{user_id}'"}
    except HTTPException:
        raise
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HTTPException(status_code=409, detail="Word already exists in the main table")
        logging.error(f"Error restoring word: {str(exc)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


def purge_words(user_id: str, lang: str):
    logging.info(f"Purging all words for user {user_id} @ {lang}")
    try:
        items = _query_all(
            vocabulary_table,
            KeyConditionExpression=Key("user_id").eq(user_id)
            & Key("word_key").begins_with(f"{lang.strip().upper()}#"),
        )
        with vocabulary_table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"user_id": item["user_id"], "word_key": item["word_key"]})
        return {"deleted": len(items)}
    except Exception as exc:
        logging.error(f"Error purging words: {str(exc)}")
        raise HTTPException(status_code=500, detail="Error purging words")


def reset_word(user_id: str, lang: str, word: str):
    logging.info(f"Resetting word {user_id} @ {lang} - {word}")
    try:
        result = get_word(user_id, lang, word)
        if not result:
            logging.warning(f"Word {word} not found for reset")
            raise HTTPException(status_code=404, detail="Word not found")
        result.status = StatusEnum.NEW
        result.lastTest = None
        result.testResults = []
        save_word(user_id, result, allow_overwrite=True)
        return {"status": "ok", "message": f"Word '{result.word}' reset for user '{user_id}'"}
    except ClientError as exc:
        logging.error(f"Error resetting word: {str(exc)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


def save_word(user_id: str, word_result: WordResult, allow_overwrite: bool = False):
    logging.info(f"Saving word {user_id} @ {word_result.language} - {word_result.word}")
    key = {"user_id": user_id, "word_key": word_key(word_result.language, word_result.word)}
    try:
        existing_item = vocabulary_table.get_item(Key=key).get("Item")
        if existing_item:
            if not allow_overwrite:
                logging.warning("Word already exists and overwrite is not allowed")
                raise HTTPException(status_code=409, detail="Word already exists for this user/language.")
            vocabulary_table.update_item(
                Key=key,
                UpdateExpression="SET #status = :status, #last_test = :last_test, #test_results = :test_results",
                ExpressionAttributeNames={"#status": "status", "#last_test": "last_test", "#test_results": "test_results"},
                ExpressionAttributeValues={
                    ":status": word_result.status.value if hasattr(word_result.status, "value") else word_result.status,
                    ":last_test": int(word_result.lastTest.timestamp()) if word_result.lastTest else None,
                    ":test_results": word_result.testResults or [],
                },
            )
        else:
            now = int(datetime.now().timestamp())
            vocabulary_table.put_item(
                Item={
                    **key,
                    "word": word_result.word.lower(),
                    "lang": word_result.language,
                    "meanings": [meaning.dict() for meaning in word_result.meanings],
                    "created_at": now,
                    "status": StatusEnum.NEW.value,
                    "last_test": now,
                    "test_results": [],
                    "schema": "v2",
                },
                ConditionExpression="attribute_not_exists(user_id) AND attribute_not_exists(word_key)",
            )
        return {"status": "ok", "message": f"Word '{word_result.word}' saved for user '{user_id}'"}
    except HTTPException:
        raise
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logging.warning("Word already exists")
            raise HTTPException(status_code=409, detail="Word already exists for this user/language.")
        logging.error(f"Error saving word: {str(exc)}")
        raise HTTPException(status_code=500, detail="Error saving word")


def get_testable_words(user_id: str, lang: str, status_days: dict):
    logging.info(f"Querying words for user {user_id} @ {lang} with status_days: {status_days}")
    try:
        current_time = int(time.time())
        filter_expressions = []
        for status, days in status_days.items():
            threshold = current_time - (days * 86400)
            filter_expressions.append(
                Attr("status").eq(status)
                & (Attr("last_test").eq(None) | Attr("last_test").lte(threshold))
            )
        query_args = {
            "KeyConditionExpression": Key("user_id").eq(user_id)
            & Key("word_key").begins_with(f"{lang.strip().upper()}#"),
        }
        if filter_expressions:
            combined_filter = filter_expressions[0]
            for expression in filter_expressions[1:]:
                combined_filter |= expression
            query_args["FilterExpression"] = combined_filter
        items = _query_all(vocabulary_table, **query_args)
        logging.info(f"Retrieved {len(items)} words for user {user_id} @ {lang} with status_days: {status_days}")
        return [convert_to_result(item) for item in items]
    except Exception as exc:
        logging.error(f"Error querying words by status and last_test: {str(exc)}")
        raise HTTPException(status_code=500, detail="Error querying words by status and last_test")


def store_challenge(user_id: str, lang: str, description: str, word: str):
    challenge_id = str(uuid.uuid4())
    try:
        challenge_table.put_item(Item={
            "user_id": user_id,
            "challenge_id": challenge_id,
            "description": description,
            "word": word.lower(),
            "lang": lang,
            "created_at": int(datetime.now().timestamp()),
            "tries": 0,
            "ttl": int(time.time()) + 3600,
        })
        return challenge_id
    except ClientError as exc:
        logging.error(f"Error storing challenge: {str(exc)}")
        raise HTTPException(status_code=500, detail="Error storing challenge")


def load_challenge_result(user_id: str, challenge_id: str):
    try:
        response = challenge_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("challenge_id").eq(challenge_id)
        )
        items = response.get("Items", [])
        if not items:
            logging.error(f"Challenge {challenge_id} not found for user {user_id}")
            raise HTTPException(status_code=404, detail="Error loading challenge")
        return items[0]
    except ClientError as exc:
        logging.error(f"Error loading challenge: {str(exc)}")
        raise HTTPException(status_code=500, detail="Error loading challenge")


def increment_challenge_tries(user_id: str, challenge_id: str):
    try:
        challenge_table.update_item(
            Key={"user_id": user_id, "challenge_id": challenge_id},
            UpdateExpression="SET tries = tries + :inc",
            ExpressionAttributeValues={":inc": 1},
            ReturnValues="UPDATED_NEW",
        )
    except ClientError as exc:
        logging.error(f"Error incrementing challenge tries: {str(exc)}")
        raise HTTPException(status_code=500, detail="Error incrementing challenge tries")


def delete_challenge(user_id: str, challenge_id: str):
    try:
        challenge_table.delete_item(Key={"user_id": user_id, "challenge_id": challenge_id})
        return {"status": "ok", "message": f"Challenge '{challenge_id}' deleted for user '{user_id}'"}
    except ClientError as exc:
        logging.error(f"Error deleting challenge: {str(exc)}")
        raise HTTPException(status_code=500, detail="Error deleting challenge")
