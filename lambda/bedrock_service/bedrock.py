import boto3
import os
import json
from models import WordResult
from utils import logging
import random

# Optional: store model ID in env vars or config
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
MAX_RETRIES = 3

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

def load_prompt_template_random(name: str) -> str:
    # Load files in the directory and randomly select one
    template_dir = f"resources/prompts/{name}"
    try:
        files = [f for f in os.listdir(template_dir) if f.endswith(".txt")]
        if not files:
            raise FileNotFoundError(f"No prompt templates found in {template_dir}")
        selected_file = random.choice(files)
        template_path = os.path.join(template_dir, selected_file)
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError as e:
        logging.error(f"Error loading prompt template from {template_dir}: {str(e)}")
        raise


def load_prompt_template(name: str) -> str:
    template_path = f"resources/prompts/{name}.txt"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError as e:
        logging.error(f"Error loading prompt template from {template_path}: {str(e)}")
        raise

def create_challenge(word: str) -> str | None:
    logging.info(f"Creating challenge for word {word}")
    prompt = load_prompt_template_random("create_challenge").format(word=word)
    raw_output = call_bedrock(prompt)
    return raw_output["output"]["message"]["content"][0]["text"]

def is_challenge_close(challenge: str, guess: str) -> bool:
    logging.info(f"Checking if challenge '{challenge}' is close to guess '{guess}'")
    prompt = load_prompt_template("challenge_check").format(challenge=challenge, guess=guess)
    raw_output = call_bedrock(prompt)
    return raw_output["output"]["message"]["content"][0]["text"].strip().lower() == "si"

def get_challenge_hint(challenge: str, guess: str, word: str) -> str:
    logging.info(f"Getting hint for challenge '{challenge}' with guess '{guess}' and word '{word}'")
    prompt = load_prompt_template("challenge_hint").format(challenge=challenge, guess=guess, word=word)
    raw_output = call_bedrock(prompt)
    return raw_output["output"]["message"]["content"][0]["text"].strip()

def describe_word(definition: str, exclusions: list[str]) -> WordResult | None:
    logging.info(f"Describing word from definition {definition} with exclusions {exclusions}")

    if not exclusions:
        prompt = load_prompt_template("describe_word").format(definition=definition)
    else:
        prompt = load_prompt_template("describe_word_exclusions").format(
            definition=definition,
            exclusions=", ".join(exclusions)
        )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            parsed = call_bedrock_json(prompt)

            if parsed is None:
                logging.warning(f"Failed to parse JSON response from Bedrock at attempt {attempt}, retrying")
                continue

            if exclusions is not None and parsed["word"] in exclusions:
                logging.warning(f"Exclusion word found in response at attempt {attempt}, retrying")
                continue

            # Fill in other meanings
            for inner_attempt in range(1, MAX_RETRIES + 1):
                enhance_prompt = load_prompt_template("add_other_meanings").format(json=json.dumps(parsed), word=parsed["word"])

                parsed_m = call_bedrock_json(enhance_prompt)

                if parsed_m is None:
                    logging.warning(f"Failed to parse JSON response from Bedrock at attempt {inner_attempt}, retrying")
                    continue

                if parsed_m["word"] != parsed["word"]:
                    logging.warning(f"Exclusion word found in response at attempt {inner_attempt}, retrying")

                return WordResult(**parsed)
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON response from Bedrock attempt {attempt}: {str(e)}")

    logging.warning(f"Failed to describe word after {MAX_RETRIES} attempts")
    return None

def call_bedrock_json(prompt: str, temperature=0.9, max_tokens=500):
    possible_json = call_bedrock(prompt, temperature, max_tokens)
    try:
        logging.info(f"Raw response from Bedrock: {possible_json}")
        raw_text = possible_json["output"]["message"]["content"][0]["text"]
        result = extract_json_from_reply(raw_text)
        return result
    except ValueError | json.JSONDecodeError as e:
        logging.info(f"Failed to parse JSON response - trying to run it through cleanup: {str(e)}")
        cleanup_prompt = load_prompt_template("clean_json").format(output=possible_json["output"]["message"]["content"][0]["text"])
        cleanup_response = call_bedrock(cleanup_prompt, temperature, max_tokens)
        logging.info(f"Raw response from Bedrock after cleanup: {cleanup_response}")
        try:
            cleanup_text = cleanup_response["output"]["message"]["content"][0]["text"]
            result = extract_json_from_reply(cleanup_text)
            return result
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON response after cleanup: {str(e)}")
            return None


def extract_json_from_reply(response):
    # Remove anything before first { and after last }
    start = response.find("{")
    end = response.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Invalid JSON format: no braces found")
    result = json.loads(response[start:end + 1])
    return result


def call_bedrock(prompt: str, temperature=0.9, max_tokens=500):
    try:
        logging.debug(f"Calling Bedrock with prompt: {prompt}")

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
                        "topP": 0.95,
                        "top_k": 50
                    }
                }),
                "utf-8"
            ),
            contentType="application/json",
            accept="application/json"
        )

        response_body = response["body"].read().decode("utf-8")
        result = json.loads(response_body)

        logging.debug(f"Received response from Bedrock: {result}")

        return result
    except Exception as e:
        logging.exception(f"Error calling Bedrock model: {str(e)}")
        raise
