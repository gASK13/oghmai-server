import random
from datetime import datetime

import bedrock_service
import db_service
from models import *
from utils import logging

FILTER = {
    StatusEnum.NEW: 1,
    StatusEnum.LEARNED: 3,
    StatusEnum.KNOWN: 7,
    StatusEnum.MASTERED: 14,
}

MAX_MISSES = 2

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
    desc = bedrock_service.create_challenge(word.word)

    # store
    ch_id = db_service.store_challenge(user_id, word.language, desc, word.word)
    logging.info(f"Stored challenge {ch_id} ({desc}) for user {user_id} @ {lang}")
    return TestChallenge(description=desc, id=ch_id)


def validate_test(user_id: str, challenge_id: str, guess: str):
    logging.info(f"Validating test {challenge_id} for user {user_id}")
    guess = guess.strip().lower()
    # get challenge
    challenge = db_service.load_challenge_result(user_id, challenge_id)

    # validate directly
    if guess == challenge["word"]:
        logging.info(f"Correct test {challenge_id} for user {user_id}")
        word = db_service.get_word(user_id, challenge["lang"], challenge["word"])
        word.testResults.append(True)
        word.testResults = word.testResults[-3:]
        word.lastTest = datetime.now()
        old_status = word.status

        # If all 3 last results have been True, raise the level
        if len(word.testResults) == 3 and all(word.testResults):
            word.status = word.status.raise_level()
            if word.status != old_status:
                logging.info(f"Raising level for word {word.word} @ {word.language} for user {user_id}")
                word.testResults = []

        db_service.save_word(user_id, word, allow_overwrite=True)
        db_service.delete_challenge(user_id, challenge_id)
        return TestResult(result=ResultEnum.CORRECT, word=challenge["word"], newStatus=word.status, oldStatus=old_status)

    # validate "similarity"
    if challenge["tries"] < MAX_MISSES and bedrock_service.is_challenge_close(challenge["description"], guess):
        db_service.increment_challenge_tries(user_id, challenge_id)
        logging.info(f"Close guess {guess} for {challenge_id} for user {user_id}")
        return TestResult(result=ResultEnum.PARTIAL)

    # totally wrong?
    word = db_service.get_word(user_id, challenge["lang"], challenge["word"])
    word.testResults.append(False)
    word.testResults = word.testResults[-3:]
    word.lastTest = datetime.now()
    old_status = word.status

    # If all 3 last results have been True, raise the level
    if len(word.testResults) == 3 and not any(word.testResults):
        word.status = word.status.lower_level()
        if word.status != old_status:
            logging.info(f"Lowering level for word {word.word} @ {word.language} for user {user_id}")
            word.testResults = []

    db_service.save_word(user_id, word, allow_overwrite=True)
    db_service.delete_challenge(user_id, challenge_id)
    return TestResult(result=ResultEnum.INCORRECT, word=challenge["word"], newStatus=word.status, oldStatus=old_status)





