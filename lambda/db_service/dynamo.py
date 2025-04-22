import boto3
from botocore.exceptions import ClientError
from models import WordResult
import os
from fastapi import HTTPException
from boto3.dynamodb.conditions import Key, Attr
import time
from utils import logging

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table_name = os.getenv("DYNAMODB_TABLE", "oghmai_vocabulary_words")
table = dynamodb.Table(table_name)

def get_words(user_id: str, lang: str):
    logging.info(f"Getting all words for user", {
        "user_id": user_id,
        "lang": lang
    })

    try:
        logging.debug(f"Querying DynamoDB for words", {
            "user_id": user_id,
            "lang": lang,
            "table": table_name
        })

        response = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id),
            FilterExpression=Attr("lang").eq(lang)
        )
        items = [item["word"] for item in response.get("Items", [])]

        logging.info(f"Retrieved words for user", {
            "user_id": user_id,
            "lang": lang,
            "count": len(items)
        })

        return items
    except Exception as e:
        logging.error(f"Error retrieving words", {
            "user_id": user_id,
            "lang": lang,
            "error_message": str(e)
        })
        raise HTTPException(status_code=500, detail="Error retrieving words")

def get_word(user_id: str, lang: str, word: str):
    logging.info(f"Getting word details", {
        "user_id": user_id,
        "lang": lang,
        "word": word
    })

    try:
        logging.debug(f"Querying DynamoDB for word", {
            "user_id": user_id,
            "lang": lang,
            "word": word,
            "table": table_name
        })

        response = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("word").eq(word.lower()),
            FilterExpression=Attr("lang").eq(lang)
        )

        items = response.get("Items", [])
        if not items:
            logging.info(f"Word not found", {
                "user_id": user_id,
                "lang": lang,
                "word": word
            })
            return None

        item = items[0]
        word_result = WordResult(
            word=item["word"],
            language=item["lang"],
            translation=item["translation"],
            definition=item["definition"],
            examples=item["examples"],
            saved=True
        )

        logging.info(f"Word found", {
            "user_id": user_id,
            "lang": lang,
            "word": word
        })

        return word_result
    except Exception as e:
        logging.error(f"Error retrieving word", {
            "user_id": user_id,
            "lang": lang,
            "word": word,
            "error_message": str(e)
        })
        raise HTTPException(status_code=500, detail="Error retrieving word")

def delete_word(user_id: str, lang: str, word: str):
    logging.info(f"Deleting word", {
        "user_id": user_id,
        "lang": lang,
        "word": word
    })

    try:
        # Fetch the item before deleting
        response = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("word").eq(word.lower()),
            FilterExpression=Attr("lang").eq(lang)
        )
        items = response.get("Items", [])
        if not items:
            logging.warning(f"Word not found for deletion", {
                "user_id": user_id,
                "lang": lang,
                "word": word
            })
            raise HTTPException(status_code=404, detail="Word not found")

        # Save the item to the recycle bin with TTL set to 1 hour
        recycle_bin_table = dynamodb.Table("oghmai_vocabulary_recycle_bin")
        ttl = int(time.time()) + 3600  # 1 hour from now
        item = items[0]
        item["ttl"] = ttl

        logging.debug(f"Moving word to recycle bin", {
            "user_id": user_id,
            "lang": lang,
            "word": word,
            "ttl": ttl
        })

        recycle_bin_table.put_item(Item=item)  # Overwrites if the same word exists

        # Delete the item from the main table
        logging.debug(f"Deleting word from main table", {
            "user_id": user_id,
            "lang": lang,
            "word": word,
            "table": table_name
        })

        table.delete_item(
            Key={
                "user_id": user_id,
                "word": word.lower()
            },
            ConditionExpression=Attr("lang").eq(lang)
        )

        logging.info(f"Word deleted successfully", {
            "user_id": user_id,
            "lang": lang,
            "word": word
        })

        return {"status": "ok", "message": f"Word '{word}' deleted for user '{user_id}'"}
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logging.warning(f"Conditional check failed when deleting word", {
                "user_id": user_id,
                "lang": lang,
                "word": word,
                "error_code": e.response["Error"]["Code"]
            })
            raise HTTPException(status_code=404, detail="Word not found.")
        else:
            logging.error(f"Error deleting word", {
                "user_id": user_id,
                "lang": lang,
                "word": word,
                "error_code": e.response["Error"]["Code"] if "Error" in e.response else "Unknown",
                "error_message": str(e)
            })
            raise HTTPException(status_code=500, detail="Internal Server Error")

def undelete_word(user_id: str, lang: str, word: str):
    logging.info(f"Undeleting word", {
        "user_id": user_id,
        "lang": lang,
        "word": word
    })

    try:
        # Fetch the item from the recycle bin
        recycle_bin_table = dynamodb.Table("oghmai_vocabulary_recycle_bin")

        logging.debug(f"Querying recycle bin for word", {
            "user_id": user_id,
            "lang": lang,
            "word": word
        })

        response = recycle_bin_table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("word").eq(word.lower()),
            FilterExpression=Attr("lang").eq(lang)
        )
        items = response.get("Items", [])
        if not items:
            logging.warning(f"Word not found in recycle bin", {
                "user_id": user_id,
                "lang": lang,
                "word": word
            })
            raise HTTPException(status_code=404, detail="Word not found in recycle bin")

        # Check if the word already exists in the main table
        logging.debug(f"Checking if word already exists in main table", {
            "user_id": user_id,
            "lang": lang,
            "word": word,
            "table": table_name
        })

        main_table_response = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id) & Key("word").eq(word.lower()),
            FilterExpression=Attr("lang").eq(lang)
        )
        if main_table_response.get("Items"):
            logging.warning(f"Word already exists in main table", {
                "user_id": user_id,
                "lang": lang,
                "word": word
            })
            raise HTTPException(status_code=409, detail="Word already exists in the main table")

        # Restore the item to the main table
        item = items[0]

        logging.debug(f"Restoring word to main table", {
            "user_id": user_id,
            "lang": lang,
            "word": word,
            "table": table_name
        })

        table.put_item(Item=item)

        # Delete the item from the recycle bin
        logging.debug(f"Removing word from recycle bin", {
            "user_id": user_id,
            "lang": lang,
            "word": word
        })

        recycle_bin_table.delete_item(
            Key={
                "user_id": user_id,
                "word": word.lower()
            }
        )

        logging.info(f"Word restored successfully", {
            "user_id": user_id,
            "lang": lang,
            "word": word
        })

        return {"status": "ok", "message": f"Word '{word}' restored for user '{user_id}'"}
    except ClientError as e:
        logging.error(f"Error restoring word", {
            "user_id": user_id,
            "lang": lang,
            "word": word,
            "error_message": str(e)
        })
        raise HTTPException(status_code=500, detail="Internal Server Error")

def purge_words(user_id: str, lang: str):
    logging.info(f"Purging all words for user", {
        "user_id": user_id,
        "lang": lang
    })

    logging.debug(f"Querying words to purge", {
        "user_id": user_id,
        "lang": lang,
        "table": table_name
    })

    response = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        FilterExpression=Attr("lang").eq(lang)
    )

    items_to_delete = response.get("Items", [])

    logging.info(f"Found words to purge", {
        "user_id": user_id,
        "lang": lang,
        "count": len(items_to_delete)
    })

    # Step 2: Batch delete items
    try:
        logging.debug(f"Starting batch delete operation", {
            "user_id": user_id,
            "lang": lang,
            "count": len(items_to_delete)
        })

        with table.batch_writer() as batch:
            for item in items_to_delete:
                batch.delete_item(
                    Key={
                        "user_id": item["user_id"],
                        "word": item["word"]
                    }
                )

        logging.info(f"Successfully purged words", {
            "user_id": user_id,
            "lang": lang,
            "count": len(items_to_delete)
        })

        return {"deleted": len(items_to_delete)}
    except Exception as e:
        logging.error(f"Error purging words", {
            "user_id": user_id,
            "lang": lang,
            "count": len(items_to_delete),
            "error_message": str(e)
        })
        raise HTTPException(status_code=500, detail="Error purging words")

def save_word(user_id: str, word_result: WordResult):
    logging.info(f"Saving word", {
        "user_id": user_id,
        "word": word_result.word,
        "lang": word_result.language
    })

    try:
        logging.debug(f"Putting item in DynamoDB", {
            "user_id": user_id,
            "word": word_result.word,
            "lang": word_result.language,
            "table": table_name
        })

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

        logging.info(f"Word saved successfully", {
            "user_id": user_id,
            "word": word_result.word,
            "lang": word_result.language
        })

        return {"status": "ok", "message": f"Word '{word_result.word}' saved for user '{user_id}'"}
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logging.warning(f"Word already exists", {
                "user_id": user_id,
                "word": word_result.word,
                "lang": word_result.language,
                "error_code": e.response["Error"]["Code"]
            })
            raise HTTPException(status_code=409, detail="Word already exists for this user/language.")
        else:
            logging.error(f"Error saving word", {
                "user_id": user_id,
                "word": word_result.word,
                "lang": word_result.language,
                "error_code": e.response["Error"]["Code"] if "Error" in e.response else "Unknown",
                "error_message": str(e)
            })
            raise HTTPException(status_code=500, detail="Error saving word")
