import boto3
import os
import json
from models import WordResult
from utils import logging

# Optional: store model ID in env vars or config
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
MAX_RETRIES = 3

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")


def load_prompt_template(name: str) -> str:
    template_path = f"resources/prompts/{name}.txt"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logging.error(f"Prompt template not found", {
            "template_name": name,
            "template_path": template_path
        })
        raise


def describe_word(definition: str, exclusions: list[str]) -> WordResult | None:
    logging.info(f"Describing word from definition", {
        "definition_length": len(definition),
        "exclusions_count": len(exclusions) if exclusions else 0
    })

    if not exclusions:
        prompt = load_prompt_template("describe_word").format(definition=definition)
    else:
        prompt = load_prompt_template("describe_word_exclusions").format(
            definition=definition,
            exclusions=", ".join(exclusions)
        )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logging.debug(f"Sending prompt to Bedrock (attempt {attempt}/{MAX_RETRIES})", {
                "prompt_length": len(prompt),
                "attempt": attempt,
                "max_retries": MAX_RETRIES
            })

            raw_output = call_bedrock(prompt)

            logging.debug(f"Received response from Bedrock", {
                "response_size": len(str(raw_output)),
                "attempt": attempt
            })

            parsed = json.loads(raw_output["output"]["message"]["content"][0]["text"])  # reverse engineered for now

            logging.debug(f"Parsed Bedrock response", {
                "word": parsed.get("word"),
                "language": parsed.get("language"),
                "attempt": attempt
            })

            if exclusions is not None and parsed["word"] in exclusions:
                logging.warning(f"Exclusion word found in response, retrying", {
                    "word": parsed["word"],
                    "attempt": attempt,
                    "max_retries": MAX_RETRIES
                })
                continue

            return WordResult(**parsed)

        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON response from Bedrock", {
                "error": str(e),
                "attempt": attempt,
                "max_retries": MAX_RETRIES
            })

    logging.warning(f"Failed to describe word after {MAX_RETRIES} attempts", {
        "definition_length": len(definition),
        "exclusions_count": len(exclusions) if exclusions else 0
    })
    return None


def call_bedrock(prompt: str, temperature=0.7, max_tokens=500):
    try:
        logging.debug(f"Calling Bedrock model", {
            "model_id": BEDROCK_MODEL_ID,
            "temperature": temperature,
            "max_tokens": max_tokens
        })

        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=bytes(
                json.dumps({
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"text": prompt}
                            ]
                        }
                    ],
                    "inferenceConfig": {
                        "maxTokens": max_tokens,
                        "stopSequences": [],
                        "temperature": temperature,
                        "topP": 0.9
                    }
                }),
                "utf-8"
            ),
            contentType="application/json",
            accept="application/json"
        )

        response_body = response["body"].read().decode("utf-8")
        result = json.loads(response_body)

        logging.debug(f"Bedrock model call successful", {
            "model_id": BEDROCK_MODEL_ID,
            "response_size": len(response_body)
        })

        return result
    except Exception as e:
        logging.exception(f"Error calling Bedrock model", {
            "model_id": BEDROCK_MODEL_ID,
            "error": str(e)
        })
        raise
