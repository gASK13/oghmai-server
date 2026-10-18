import json
import os
import random

import boto3
from pydantic import ValidationError

from language_support import get_language, normalize_text
from models import ExplanationResponse, WordResult, WordTypeEnum
from utils import logging

BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-5-5")
MAX_RETRIES = 3
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")


def _localized_prompt_name(name: str, language: str) -> str:
    code = get_language(language).code.lower()
    return name if code == "it" else f"{name}_{code}"


def load_prompt_template_random(name: str) -> str:
    template_dir = f"resources/prompts/{name}"
    files = [f for f in os.listdir(template_dir) if f.endswith(".txt")]
    if not files:
        raise FileNotFoundError(f"No prompt templates found in {template_dir}")
    template_path = os.path.join(template_dir, random.choice(files))
    with open(template_path, "r", encoding="utf-8") as prompt_file:
        return prompt_file.read()


def load_prompt_template(name: str) -> str:
    template_path = f"resources/prompts/{name}.txt"
    with open(template_path, "r", encoding="utf-8") as prompt_file:
        return prompt_file.read()


def _output_text(response) -> str:
    return response["output"]["message"]["content"][0]["text"].strip()


def create_challenge(word: str, language: str = "IT") -> str | None:
    code = get_language(language).code
    logging.info(f"Creating {code} challenge for word {word}")
    prompt_name = _localized_prompt_name("create_challenge", code)
    prompt = load_prompt_template_random(prompt_name).format(word=word)
    return _output_text(call_bedrock(prompt))


def is_challenge_close(challenge: str, guess: str, language: str = "IT") -> bool:
    lang = get_language(language)
    prompt_name = _localized_prompt_name("challenge_check", lang.code)
    if lang.code == "IT":
        prompt = load_prompt_template(prompt_name).format(challenge=challenge, guess=guess)
    else:
        prompt = load_prompt_template(prompt_name).format(challenge=challenge, guess=guess)
    token = normalize_text(_output_text(call_bedrock(prompt)))
    return token == normalize_text(lang.yes_token)


def get_challenge_hint(challenge: str, guess: str, word: str, language: str = "IT") -> str:
    lang = get_language(language)
    prompt_name = _localized_prompt_name("challenge_hint", lang.code)
    prompt = load_prompt_template(prompt_name).format(challenge=challenge, guess=guess, word=word)
    return _output_text(call_bedrock(prompt))


def _validated_word_result(data, language: str) -> WordResult:
    if not isinstance(data, dict):
        raise TypeError("Bedrock response must be a JSON object")
    # The model is never authoritative for the language field.
    safe_data = dict(data)
    safe_data["language"] = get_language(language).code
    return WordResult.model_validate(safe_data)


def _meaning_key(meaning) -> tuple[str, str, str]:
    return (
        normalize_text(meaning.translation),
        normalize_text(meaning.definition),
        meaning.type.value,
    )


def describe_word(definition: str, exclusions: list[str] | None = None, language: str = "IT") -> WordResult | None:
    lang = get_language(language)
    exclusions = exclusions or []
    logging.info(f"Describing {lang.code} word from definition {definition}")

    suffix = "" if lang.code == "IT" else f"_{lang.code.lower()}"
    if exclusions:
        prompt = load_prompt_template(f"describe_word_exclusions{suffix}").format(
            definition=definition,
            exclusions=", ".join(exclusions),
        )
    else:
        prompt = load_prompt_template(f"describe_word{suffix}").format(definition=definition)

    excluded = {normalize_text(item) for item in exclusions}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            parsed = call_bedrock_json(prompt)
            if parsed is None:
                continue
            result = _validated_word_result(parsed, lang.code)
            if normalize_text(result.word) in excluded:
                logging.warning(f"Excluded word returned at attempt {attempt}; retrying")
                continue

            enhance_prompt = load_prompt_template(f"add_other_meanings{suffix}").format(
                json=json.dumps(result.model_dump(mode="json", exclude={"language", "status", "createdAt", "lastTest", "testResults"}), ensure_ascii=False),
                word=result.word,
            )
            for inner_attempt in range(1, MAX_RETRIES + 1):
                try:
                    enriched_data = call_bedrock_json(enhance_prompt)
                    if enriched_data is None:
                        continue
                    enriched = _validated_word_result(enriched_data, lang.code)
                    if normalize_text(enriched.word) != normalize_text(result.word):
                        logging.warning(f"Enrichment changed the lemma at attempt {inner_attempt}; retrying")
                        continue
                    if normalize_text(enriched.word) in excluded:
                        continue
                    meanings = list(result.meanings)
                    known = {_meaning_key(item) for item in meanings}
                    for meaning in enriched.meanings:
                        key = _meaning_key(meaning)
                        if key not in known:
                            meanings.append(meaning)
                            known.add(key)
                    result.meanings = meanings
                    break
                except (ValidationError, ValueError, TypeError, KeyError) as exc:
                    logging.warning(f"Invalid enrichment response at attempt {inner_attempt}: {exc}")
            return result
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            logging.warning(f"Invalid Bedrock word response at attempt {attempt}: {exc}")

    logging.warning(f"Failed to describe word after {MAX_RETRIES} attempts")
    return None


def call_bedrock_json(prompt: str, temperature=0.9, max_tokens=500):
    try:
        response = call_bedrock(prompt, temperature, max_tokens)
        return extract_json_from_reply(_output_text(response))
    except (ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
        logging.info(f"Failed to parse Bedrock JSON; attempting cleanup: {exc}")
        try:
            raw = _output_text(response)
            cleanup_prompt = load_prompt_template("clean_json").format(output=raw)
            cleanup_response = call_bedrock(cleanup_prompt, temperature, max_tokens)
            return extract_json_from_reply(_output_text(cleanup_response))
        except (ValueError, json.JSONDecodeError, KeyError, TypeError, UnboundLocalError) as cleanup_exc:
            logging.warning(f"Failed to parse Bedrock JSON after cleanup: {cleanup_exc}")
            return None


def extract_json_from_reply(response: str):
    start = response.find("{")
    end = response.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Invalid JSON format: no JSON object found")
    result = json.loads(response[start:end + 1])
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")
    return result


def get_verb_explanation(word: WordResult) -> ExplanationResponse | None:
    lang = get_language(word.language)
    if not lang.supports_verb_forms:
        return None
    if not any(meaning.type == WordTypeEnum.VERB for meaning in word.meanings):
        logging.warning("Only VERB type is supported for explanations")
        return None

    prompt = load_prompt_template("verb_forms").format(verb=word.word)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            parsed = call_bedrock_json(prompt)
            if isinstance(parsed, dict):
                return ExplanationResponse(word=word.word, type=WordTypeEnum.VERB, explanations=parsed)
        except (ValidationError, ValueError, TypeError) as exc:
            logging.warning(f"Invalid verb explanation at attempt {attempt}: {exc}")
    return None


def call_bedrock(prompt: str, temperature=0.9, max_tokens=500):
    try:
        return bedrock.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={
                "maxTokens": max_tokens,
                "temperature": temperature,
                "topP": 0.95,
            },
        )
    except Exception as exc:
        logging.exception(f"Error calling Bedrock model: {exc}")
        raise
