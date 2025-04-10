import boto3
import os
import json
from models import WordResult

# Optional: store model ID in env vars or config
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
MAX_RETRIES = 3

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

def load_prompt_template(name: str) -> str:
    with open(f"resources/prompts/{name}.txt", "r", encoding="utf-8") as f:
        return f.read()

def bedrock_describe_word(definition: str) -> WordResult:
    prompt = load_prompt_template("describe_word").format(definition=definition)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw_output = call_bedrock(prompt)
            parsed = json.loads(raw_output["completion"])  # assumes Claude-style response
            return WordResult(**parsed)

        except json.JSONDecodeError as e:
            print(f"[Attempt {attempt}] Invalid response: {e}")
            if attempt == MAX_RETRIES:
                raise RuntimeError("Failed to get a valid response from Bedrock after multiple attempts.")

def call_bedrock(prompt: str, temperature=0.7, max_tokens=500):
    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=bytes(
            json.dumps({
                "prompt": prompt,
                "temperature": temperature,
                "max_tokens_to_sample": max_tokens,
                "stop_sequences": ["\n\n"]
            }),
            "utf-8"
        ),
        contentType="application/json",
        accept="application/json",
    )
    response_body = response["body"].read().decode("utf-8")
    return json.loads(response_body)
