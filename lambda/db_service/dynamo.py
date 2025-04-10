import boto3
from botocore.exceptions import ClientError
from models import WordResult
import os

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table_name = os.getenv("DYNAMODB_TABLE", "oghmai_vocabulary_words")
table = dynamodb.Table(table_name)

def save_word(user_id: str, word_result: WordResult):
    try:
        table.put_item(
            Item={
                "user_id": user_id,
                "word": word_result.word,
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
            return {"status": "exists", "message": "Word already exists for this user/language."}
        raise

