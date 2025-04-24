import random
from datetime import datetime

import db_service
import bedrock_service
from fastapi import HTTPException
from models import *
from utils import logging

FILTER = {
    StatusEnum.NEW: 1,
    StatusEnum.LEARNED: 3,
    StatusEnum.KNOWN: 7,
    StatusEnum.MASTERED: 14,
}

def get_statistics(user_id: str, lang: str):
    logging.info(f"Getting statistics for user {user_id} @ {lang}")
    words = db_service.get_testable_words(user_id, lang, FILTER)
    response =  TestStatistics()

    # group by word.status in words in response.available
    for word in words:
        response.available[word.status] += 1

    return response

def get_next_test(user_id: str, lang: str):
    logging.info(f"Getting next test for user {user_id} @ {lang}")
    words = db_service.get_testable_words(user_id, lang, FILTER)

    if not words:
        logging.info(f"No words available for user {user_id} @ {lang}")
        return None

    # select random word
    word = random.choice(words)

    # get from bedrock
    # TODO BEDROCK CALL
    desc = f"Lorem Ipsum {word}"

    # store
    ch_id = db_service.store_challenge(user_id, word.language, desc, word.word)
    logging.info(f"Stored challenge {ch_id} ({desc}) for user {user_id} @ {lang}")
    return TestChallenge(description=desc, id=ch_id)


def validate_test(user_id: str, challenge_id: str, guess: str):
    logging.info(f"Validating test {challenge_id} for user {user_id}")
    # get challenge
    challenge, lang = db_service.load_challenge_result(user_id, challenge_id)

    if not challenge:
        logging.error(f"Challenge {challenge_id} not found for user {user_id}")
        raise HTTPException(status_code=404, detail="Error retrieving words")

    # validate directly
    if guess == challenge:
        logging.info(f"Correct test {challenge_id} for user {user_id}")
        word = db_service.get_word(user_id, lang, challenge)
        word.testResults.append(True)
        word.testResults = word.testResults[-3:]
        word.lastTest = datetime.now()
        oldStatus = word.status

        # If all 3 last results have been True, raise the level
        if len(word.testResults) == 3 and all(word.testResults):
            word.status = word.status.raise_level()
            if word.status != oldStatus:
                logging.info(f"Raising level for word {word.word} @ {word.language} for user {user_id}")
                word.testResults = []

        db_service.save_word(user_id, word, allow_overwrite=True)
        db_service.delete_challenge(user_id, challenge_id)
        return TestResult(result=ResultEnum.CORRECT, newStatus=word.status, oldStatus=oldStatus)

    # validate "similarity"
    # TODO Bedrock

    # totally wrong?
    word = db_service.get_word(user_id, lang, challenge)
    word.testResults.append(False)
    word.testResults = word.testResults[-3:]
    word.lastTest = datetime.now()
    oldStatus = word.status

    # If all 3 last results have been True, raise the level
    if len(word.testResults) == 3 and not any(word.testResults):
        word.status = word.status.lower_level()
        if word.status != oldStatus:
            logging.info(f"Lowering level for word {word.word} @ {word.language} for user {user_id}")
            word.testResults = []

    db_service.save_word(user_id, word, allow_overwrite=True)
    db_service.delete_challenge(user_id, challenge_id)
    return TestResult(result=ResultEnum.INCORRECT, newStatus=word.status, oldStatus=oldStatus)





