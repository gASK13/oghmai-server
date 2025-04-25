from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from mangum import Mangum
from models import *
import bedrock_service
import db_service
import time
from utils import logging
import challenge_service

# FASTAPI app and AWS Lambda handler
app = FastAPI()
handler = Mangum(app)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Generate a request ID for tracking
    request_id = logging.set_request_id()

    # Log the incoming request
    start_time = time.time()
    logging.info(f"Incoming request: {request.method} {request.url}")

    try:
        # Process the request
        response = await call_next(request)

        # Log the completed request
        process_time = time.time() - start_time
        logging.info(f"Completed request: {request.method} {request.url} with {response.status_code} in {process_time:.2f} seconds")

        return response
    finally:
        # Clear the request ID after the request is complete
        logging.clear_request_id()

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log the exception with full details
    logging.exception(f"Unhandled exception at {request.method} {request.url.path} - {str(exc)}")

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.get("/test", response_model=TestStatistics)
async def get_available_tests():
    user_id = "test"
    lang = 'IT'
    return challenge_service.get_statistics(user_id, lang)


@app.get("/test/next", response_model=TestChallenge)
async def get_next_test():
    user_id = "test"
    lang = 'IT'
    next_test = challenge_service.get_next_test(user_id, lang)
    if next_test is None:
        return JSONResponse(status_code=204, content=None)
    return next_test


@app.put("/test/{id}", response_model=TestResult)
async def validate_test(id: str, guess: str):
    user_id = "test"
    return challenge_service.validate_test(user_id, id, guess)

@app.get("/words", response_model=WordList)
async def get_words():
    user_id = "test"
    lang = 'IT'
    words = db_service.get_words(user_id, lang)
    return WordList(words=words)

@app.patch("/words")
async def patch_words(action: str):
    user_id = "test"
    lang = 'IT'
    if action == "reset":
        for word in db_service.get_words(user_id, lang):
            db_service.reset_word(user_id, lang, word)
        return {"message": "Words reset"}
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

@app.get("/word/{word}", response_model=WordResult)
async def get_word(word: str):
    user_id = "test"
    lang = 'IT'
    word_result = db_service.get_word(user_id, lang, word)
    if word_result is None:
        raise HTTPException(status_code=404, detail=f"Word {word} not found")
    return word_result

@app.delete("/word/{word}")
async def get_word(word: str):
    user_id = "test"
    lang = 'IT'
    return db_service.delete_word(user_id, lang, word)

@app.patch("/word/{word}")
async def patch_word(word: str, action: str):
    user_id = "test"  # Hardcoded for now
    lang = 'IT'
    if action == "undelete":
        return db_service.undelete_word(user_id, lang, word)
    elif action == "reset":
        return db_service.reset_word(user_id, lang, word)
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

@app.post("/describe-word", response_model=WordResult)
async def describe_word(req: DescriptionRequest):
    user_id = "test"  # For now hardcoded
    result = bedrock_service.describe_word(req.description, req.exclusions)
    if result is None:
        return JSONResponse(status_code=204, content=None)
    existing_word = db_service.get_word(user_id, result.language, result.word)
    result.status = existing_word.status if existing_word else StatusEnum.UNSAVED
    return result

@app.post("/save-word")
async def save_word(word_result: WordResult):
    user_id = "test"  # For now hardcoded
    result = db_service.save_word(user_id, word_result)
    return result

@app.delete("/words")
async def delete_words():
    user_id = "test"  # For now hardcoded
    words = db_service.purge_words(user_id, 'IT')
    return words
