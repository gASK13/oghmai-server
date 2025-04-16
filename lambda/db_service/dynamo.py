import boto3
from botocore.exceptions import ClientError
import logging
from models import WordResult
import os
from fastapi import HTTPException
from boto3.dynamodb.conditions import Key, Attr
import time

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table_name = os.getenv("DYNAMODB_TABLE", "oghmai_vocabulary_words")
table = dynamodb.Table(table_name)

def get_words(user_id: str, lang: str):
    response = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        FilterExpression=Attr("lang").eq(lang)
    )
    items = [item["word"] for item in response.get("Items", [])]
    return items

def get_word(user_id: str, lang: str, word: str):
    response = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id) & Key("word").eq(word.lower()),
        FilterExpression=Attr("lang").eq(lang)
    )

    items = response.get("Items", [])
    if not items:
        raise HTTPException(status_code=404, detail="Word not found")

    item = items[0]
    word_result = WordResult(
        word=item["word"],
        language=item["lang"],
        translation=item["translation"],
        definition=item["definition"],
        examples=item["examples"]
    )
    return word_result

def delete_word(user_id: str, lang: str, word: str):
    try:
        # Fetch the item before deleting
        response = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("word").eq(word.lower()),
            FilterExpression=Attr("lang").eq(lang)
        )
        items = response.get("Items", [])
        if not items:
            raise HTTPException(status_code=404, detail="Word not found")

        # Save the item to the recycle bin with TTL set to 1 hour
        recycle_bin_table = dynamodb.Table("oghmai_vocabulary_recycle_bin")
        ttl = int(time.time()) + 3600  # 1 hour from now
        item = items[0]
        item["ttl"] = ttl
        recycle_bin_table.put_item(Item=item)  # Overwrites if the same word exists

        # Delete the item from the main table
        table.delete_item(
            Key={
                "user_id": user_id,
                "word": word.lower()
            },
            ConditionExpression=Attr("lang").eq(lang)
        )
        return {"status": "ok", "message": f"Word '{word}' deleted for user '{user_id}'"}
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HTTPException(status_code=404, detail="Word not found.")
        else:
            logging.exception("Error deleting word")
            raise HTTPException(status_code=500, detail="Internal Server Error")

def undelete_word(user_id: str, lang: str, word: str):
    try:
        # Fetch the item from the recycle bin
        recycle_bin_table = dynamodb.Table("oghmai_vocabulary_recycle_bin")
        response = recycle_bin_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("word").eq(word.lower()),
            FilterExpression=Attr("lang").eq(lang)
        )
        items = response.get("Items", [])
        if not items:
            raise HTTPException(status_code=404, detail="Word not found in recycle bin")

        # Check if the word already exists in the main table
        main_table_response = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("word").eq(word.lower()),
            FilterExpression=Attr("lang").eq(lang)
        )
        if main_table_response.get("Items"):
            raise HTTPException(status_code=409, detail="Word already exists in the main table")

        # Restore the item to the main table
        item = items[0]
        table.put_item(Item=item)

        # Delete the item from the recycle bin
        recycle_bin_table.delete_item(
            Key={
                "user_id": user_id,
                "word": word.lower()
            }
        )
        return {"status": "ok", "message": f"Word '{word}' restored for user '{user_id}'"}
    except ClientError as e:
        logging.exception("Error restoring word")
        raise HTTPException(status_code=500, detail="Internal Server Error")

def purge_words(user_id: str, lang: str):
    response = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        FilterExpression=Attr("lang").eq(lang)
    )

    items_to_delete = response.get("Items", [])

    # Step 2: Batch delete items
    with table.batch_writer() as batch:
        for item in items_to_delete:
            batch.delete_item(
                Key={
                    "user_id": item["user_id"],
                    "word": item["word"]
                }
            )

    return {"deleted": len(items_to_delete)}

def save_word(user_id: str, word_result: WordResult):
    try:
        table.put_item(
            Item={
                "user_id": user_id,
                "word": word_result.word.lower(),
                "lang": word_result.language,
                "translation": word_result.translation,
                "definition": word_result.definition,
                "examples": word_result.examples,
            },
            ConditionExpression="attribute_not_exists(user_id) AND attribute_not_exists(word) AND attribute_not_exists(lang)"
        )
        return {"status": "ok", "message": f"Word '{word_result.word}' saved for user '{user_id}'"}
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HTTPException(status_code=409, detail="Word already exists for this user/language.")

