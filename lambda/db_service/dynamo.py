import json
import uuid

import boto3
from botocore.exceptions import ClientError
from models import *
import os
from fastapi import HTTPException
from boto3.dynamodb.conditions import Key, Attr
import time
from utils import logging
from datetime import datetime, timezone

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
vocabulary_table_name = os.getenv("VOCABULARY_TABLE", "oghmai_vocabulary_words")
vocabulary_table = dynamodb.Table(vocabulary_table_name)
recycle_bin_table_name = os.getenv("TRASH_BIN_TABLE", "oghmai_vocabulary_recycle_bin")
recycle_bin_table = dynamodb.Table(recycle_bin_table_name)
challenge_table_name = os.getenv("CHALLENGE_TABLE", "oghmai_challenges")
challenge_table = dynamodb.Table(challenge_table_name)

def get_words(user_id: str, lang: str, status: str = None, failed_last_test: bool = False, contains: str = None):
    logging.info(f"Filtering words for user {user_id} @ {lang} with status={status}, failed_last_test={failed_last_test}, contains={contains}")

    try:
        # Start with a base filter expression for the language
        filter_expression = Attr("lang").eq(lang)

        # Add status filter if provided
        if status:
            try:
                status_values = [s.strip() for s in status.split(',')]
                # Validate status values
                for s in status_values:
                    # This will raise ValueError if the status is invalid
                    StatusEnum(s)

                # If there's only one status, use eq, otherwise use is_in
                if len(status_values) == 1:
                    filter_expression = filter_expression & Attr("status").eq(status_values[0])
                else:
                    filter_expression = filter_expression & Attr("status").is_in(status_values)
            except ValueError as e:
                logging.warning(f"Invalid status value in filter: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Invalid status value: {str(e)}")

        # Query the table with the filter expression
        response = vocabulary_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id),
            FilterExpression=filter_expression
        )
        items = response.get("Items", [])

        # Apply the 'contains' filter in memory
        if contains:
            items = [item for item in items if contains.lower() in item["word"].lower()]

        # Convert items to WordResult objects
        word_results = [convert_to_result(item) for item in items]

        # Apply failed_last_test filter in memory (can't be done efficiently in DynamoDB)
        if failed_last_test:
            word_results = [w for w in word_results if w.testResults and w.testResults[-1] == False]

        logging.info(f"Retrieved {len(word_results)} filtered words for user {user_id} @ {lang}")

        return [convert_result_to_item(word) for word in word_results]
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.error(f"Error filtering words for user {user_id} @ {lang}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error filtering words")

def get_word(user_id: str, lang: str, word: str):
    logging.info(f"Getting word details {user_id} @ {lang} - {word}")

    try:
        response = vocabulary_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("word").eq(word.lower()),
            FilterExpression=Attr("lang").eq(lang)
        )

        items = response.get("Items", [])
        if not items:
            logging.info(f"Word {word} not found")
            return None

        item = items[0]

        return convert_to_result(item)
    except Exception as e:
        logging.error(f"Error retrieving word: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving word")


def convert_to_result(item):
    # Not ideal, but I have divergent naming conventions in the DB
    # Will be fixed during migration and then removed!!!
    item["createdAt"] = datetime.fromtimestamp(int(item.pop("creadted_at", None))).astimezone(timezone.utc)
    item["lastTest"] = datetime.fromtimestamp(int(item.pop("last_test", None))).astimezone(timezone.utc) if item.get(
            "last_test") else None
    item["testResults"] = item.pop("test_results", None)

    word_result = WordResult(**item)

    return word_result

def convert_result_to_item(item: WordResult):
    word_item = WordItem(
        word=item.word,
        status=item.status,
        testResults=item.testResults
    )
    return word_item

def delete_word(user_id: str, lang: str, word: str):
    logging.info(f"Deleting word {user_id} @ {lang} - {word}")

    try:
        # Fetch the item before deleting
        response = vocabulary_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("word").eq(word.lower()),
            FilterExpression=Attr("lang").eq(lang)
        )
        items = response.get("Items", [])
        if not items:
            logging.warning(f"Word {word} not found for deletion")
            raise HTTPException(status_code=404, detail="Word not found")

        # Save the item to the recycle bin with TTL set to 1 hour
        ttl = int(time.time()) + 3600  # 1 hour from now
        item = items[0]
        item["ttl"] = ttl

        recycle_bin_table.put_item(Item=item)  # Overwrites if the same word exists

        vocabulary_table.delete_item(
            Key={
                "user_id": user_id,
                "word": word.lower()
            },
            ConditionExpression=Attr("lang").eq(lang)
        )

        return {"status": "ok", "message": f"Word '{word}' deleted for user '{user_id}'"}
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logging.warning(f"Conditional check failed when deleting word {e.response['Error']['Code']}")
            raise HTTPException(status_code=404, detail="Word not found.")
        else:
            logging.error(f"Error deleting word: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal Server Error")

def undelete_word(user_id: str, lang: str, word: str):
    logging.info(f"Undeleting word {user_id} @ {lang} - {word}")

    try:
        # Fetch the item from the recycle bin
        response = recycle_bin_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("word").eq(word.lower()),
            FilterExpression=Attr("lang").eq(lang)
        )
        items = response.get("Items", [])
        if not items:
            logging.warning(f"Word {word} not found in recycle bin")
            raise HTTPException(status_code=404, detail="Word not found in recycle bin")

        main_table_response = vocabulary_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("word").eq(word.lower()),
            FilterExpression=Attr("lang").eq(lang)
        )
        if main_table_response.get("Items"):
            logging.warning(f"Word already exists in main table")
            raise HTTPException(status_code=409, detail="Word already exists in the main table")

        # Restore the item to the main table
        item = items[0]
        vocabulary_table.put_item(Item=item)
        recycle_bin_table.delete_item(
            Key={
                "user_id": user_id,
                "word": word.lower()
            }
        )

        return {"status": "ok", "message": f"Word '{word}' restored for user '{user_id}'"}
    except ClientError as e:
        logging.error(f"Error restoring word: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

def purge_words(user_id: str, lang: str):
    logging.info(f"Purging all words for user {user_id} @ {lang}")

    response = vocabulary_table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        FilterExpression=Attr("lang").eq(lang)
    )

    items_to_delete = response.get("Items", [])

    # Step 2: Batch delete items
    try:
        with vocabulary_table.batch_writer() as batch:
            for item in items_to_delete:
                batch.delete_item(
                    Key={
                        "user_id": item["user_id"],
                        "word": item["word"]
                    }
                )

        return {"deleted": len(items_to_delete)}
    except Exception as e:
        logging.error(f"Error purging words: {str(e)}")
        raise HTTPException(status_code=500, detail="Error purging words")

def reset_word(user_id: str, lang: str, word: str):
    logging.info(f"Resetting word {user_id} @ {lang} - {word}")

    try:
        word = get_word(user_id, lang, word)
        if not word:
            logging.warning(f"Word {word} not found for reset")
            raise HTTPException(status_code=404, detail="Word not found")
        # Reset the word
        word.status = StatusEnum.NEW
        word.lastTest = None
        word.testResults = []
        save_word(user_id, word, allow_overwrite=True)

        return {"status": "ok", "message": f"Word '{word.word}' reset for user '{user_id}'"}
    except ClientError as e:
        logging.error(f"Error resetting word: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

def save_word(user_id: str, word_result: WordResult, allow_overwrite: bool = False):
    logging.info(f"Saving word {user_id} @ {word_result.language} - {word_result.word}")

    try:
        # If word exists, update it
        existing_response = vocabulary_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("word").eq(word_result.word.lower()),
            FilterExpression=Attr("lang").eq(word_result.language)
        )
        existing_items = existing_response.get("Items", [])
        if existing_items:
            if not allow_overwrite:
                logging.warning(f"Word already exists and overwrite is not allowed")
                raise HTTPException(status_code=409, detail="Word already exists for this user/language.")

            vocabulary_table.update_item(
                Key={
                    "user_id": user_id,
                    "word": word_result.word.lower()
                },
                UpdateExpression="SET #meanings = :meanings, #status = :status, #last_test = :last_test, "
                                 "#test_results = :test_results",
                ConditionExpression=Attr("lang").eq(word_result.language),  # Ensure lang matches
                ExpressionAttributeNames={
                    "#meanings": "meanings",
                    "#status": "status",
                    "#last_test": "last_test",
                    "#test_results": "test_results"
                },
                ExpressionAttributeValues={
                    ":meanings": word_result.meanings,
                    ":status": word_result.status,
                    ":last_test": int(word_result.lastTest.timestamp()) if word_result.lastTest else None,
                    ":test_results": word_result.testResults or []
                }
            )
        else:
            vocabulary_table.put_item(
                Item={
                    "user_id": user_id,
                    "word": word_result.word.lower(),
                    "lang": word_result.language,
                    "meanings": word_result.meanings,
                    "created_at": int(datetime.now().timestamp()),
                    "status": StatusEnum.NEW,
                    "last_test": int(datetime.now().timestamp()),
                    "test_results": [],
                },
                ConditionExpression="attribute_not_exists(user_id) AND attribute_not_exists(word) AND attribute_not_exists(lang)"
            )

        return {"status": "ok", "message": f"Word '{word_result.word}' saved for user '{user_id}'"}
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logging.warning(f"Word already exists")
            raise HTTPException(status_code=409, detail="Word already exists for this user/language.")
        else:
            logging.error(f"Error saving word: {str(e)}")
            raise HTTPException(status_code=500, detail="Error saving word")

def get_testable_words(user_id: str, lang: str, status_days: dict):
    logging.info(f"Querying words for user {user_id} @ {lang} with status_days: {status_days}")

    try:
        # Get the current timestamp
        current_time = int(time.time())

        # Build the filter expression dynamically
        filter_expressions = []
        for status, days in status_days.items():
            last_test_threshold = current_time - (days * 86400)  # Convert days to seconds
            filter_expressions.append(
                (Attr("status").eq(status) & (Attr("last_test").eq(None) | Attr("last_test").lte(last_test_threshold)))
            )

        # Combine filter expressions with OR
        combined_filter_expression = filter_expressions[0]
        for expr in filter_expressions[1:]:
            combined_filter_expression |= expr

        # Query the table
        response = vocabulary_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id),
            FilterExpression=Attr("lang").eq(lang) & combined_filter_expression
        )

        items = response.get("Items", [])

        logging.info(f"Retrieved {len(items)} words for user {user_id} @ {lang} with status_days: {status_days}")

        return [convert_to_result(item) for item in items]
    except Exception as e:
        logging.error(f"Error querying words by status and last_test: {str(e)}")
        raise HTTPException(status_code=500, detail="Error querying words by status and last_test")


def store_challenge(user_id: str, lang: str, description: str, word: str):
    # generate UUID
    challenge_id = str(uuid.uuid4())

    # save the challenge to dynamo
    try:
        challenge_table.put_item(
            Item={
                "user_id": user_id,
                "challenge_id": challenge_id,
                "description": description,
                "word": word.lower(),
                "lang": lang,
                "created_at": int(datetime.now().timestamp()),
                "tries": 0,
                "ttl": int(time.time()) + 3600,  # 1 hour from now should be enough
            }
        )

        return challenge_id
    except ClientError as e:
        logging.error(f"Error storing challenge: {str(e)}")
        raise HTTPException(status_code=500, detail="Error storing challenge")

def load_challenge_result(user_id: str, challenge_id: str):
    # load challenge from dynamo
    try:
        response = challenge_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("challenge_id").eq(challenge_id)
        )
        items = response.get("Items", [])
        if not items:
            logging.error(f"Challenge {challenge_id} not found for user {user_id}")
            raise HTTPException(status_code=404, detail="Error loading challenge")

        item = items[0]

        return item
    except ClientError as e:
        logging.error(f"Error loading challenge: {str(e)}")
        raise HTTPException(status_code=500, detail="Error loading challenge")


def increment_challenge_tries(user_id: str, challenge_id: str):
    # increment tries in dynamo
    try:
        challenge_table.update_item(
            Key={
                "user_id": user_id,
                "challenge_id": challenge_id
            },
            UpdateExpression="SET tries = tries + :inc",
            ExpressionAttributeValues={
                ":inc": 1
            },
            ReturnValues="UPDATED_NEW"
        )

        return
    except ClientError as e:
        logging.error(f"Error incrementing challenge tries: {str(e)}")
        raise HTTPException(status_code=500, detail="Error incrementing challenge tries")

def delete_challenge(user_id: str, challenge_id: str):
    # delete the challenge from dynamo
    try:
        challenge_table.delete_item(
            Key={
                "user_id": user_id,
                "challenge_id": challenge_id
            }
        )

        return {"status": "ok", "message": f"Challenge '{challenge_id}' deleted for user '{user_id}'"}
    except ClientError as e:
        logging.error(f"Error deleting challenge: {str(e)}")
        raise HTTPException(status_code=500, detail="Error deleting challenge")
