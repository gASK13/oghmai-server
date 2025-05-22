import os
import boto3
import json
import time

# Import local modules
from bedrock_service.bedrock import call_bedrock_json, load_prompt_template
from utils import logging

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
vocabulary_table_name = os.getenv("VOCABULARY_TABLE", "oghmai_vocabulary_words")
vocabulary_table = dynamodb.Table(vocabulary_table_name)

def convert_v1_to_v2(item):
    """
    Convert a V1 schema item to V2 schema
    """
    # Create a basic V2 item with a single meaning
    meaning = {
        "translation": item.get("translation", ""),
        "definition": item.get("definition", ""),
        "examples": item.get("examples", []),
        "type": "OTHER"  # Default type as string
    }

    # Create a new item with V2 schema
    v2_item = {
        "user_id": item["user_id"],
        "word": item["word"],
        "lang": item["lang"],
        "meanings": [meaning],
        "created_at": item["created_at"],
        "status": item["status"],
        "last_test": item.get("last_test"),
        "test_results": item.get("test_results", []),
        "schema": "v2"
    }

    return v2_item

def enrich_with_bedrock(item):
    """
    Use Bedrock to enrich the item with additional meanings
    """
    # Use Bedrock to enrich with other meanings
    try:
        for i in item["meanings"]:
            i["type"] = "OTHER"

        enhance_prompt = load_prompt_template("add_other_meanings").format(
            json=json.dumps({"word" : item["word"], "meanings": item["meanings"]}),
            word=item["word"]
        )

        enriched_data = call_bedrock_json(enhance_prompt)

        if enriched_data and "meanings" in enriched_data and len(enriched_data["meanings"]) > 0:
            # Update the meanings in the item
            item["meanings"] = enriched_data["meanings"]
            return True
    except Exception as e:
        logging.error(f"Error enriching item with Bedrock: {str(e)}")
        raise

    return False

def update_item_in_dynamodb(item):
    """
    Update the item in DynamoDB with the V2 schema
    """
    try:
        vocabulary_table.put_item(Item=item)
        return True
    except Exception as e:
        logging.error(f"Error updating item in DynamoDB: {str(e)}")
        return False

def scan_v1_items():
    """
    Scan DynamoDB for V1 items (those without a schema field)
    """
    items = []
    last_evaluated_key = None

    scan_kwargs = {
        "FilterExpression": "attribute_not_exists(#schema)",
        "ExpressionAttributeNames": {"#schema": "schema"}
    }

    count = 0

    while True:
        if last_evaluated_key:
            scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

        response = vocabulary_table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))

        count += len(response.get("Items", []))

        last_evaluated_key = response.get("LastEvaluatedKey")

        if not last_evaluated_key:
            break

    return items

def update_v1_to_v2(item):
    # Convert to V2 schema
    v2_item = convert_v1_to_v2(item)
    enrich_with_bedrock(v2_item)
    update_item_in_dynamodb(v2_item)

def main():
    # Here should be "loop over versions"

    # Scan for V1 items
    logging.info("Scanning for V1 items...")
    v1_items = scan_v1_items()
    logging.info(f"Found {len(v1_items)} V1 items")

    # Process items in batches
    for i in v1_items:
        update_v1_to_v2(i)
        # Sleep briefly to avoid overwhelming the API
        time.sleep(1)

    # Print statistics
    logging.info("Migration complete!")

if __name__ == "__main__":
    main()
