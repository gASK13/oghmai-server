from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from mangum import Mangum
import boto3
from models import *
import bedrock_service
import db_service
import logging
import time

app = FastAPI()
handler = Mangum(app)
client = boto3.client("bedrock-runtime", region_name="us-east-1")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logging.info(f"Incoming request: {request.method} {request.url}")
    response = await call_next(request)
    process_time = time.time() - start_time
    logging.info(
        f"Completed request: {request.method} {request.url} in {process_time:.2f}s with status {response.status_code}")
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.exception(f"Unhandled exception at {request.method} {request.url.path}")
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

@app.get("/words", response_model=WordList)
async def get_words():
    user_id = "test"
    lang = 'IT'
    words = db_service.get_words(user_id, lang)
    return WordList(words=words)

@app.get("/word/{word}", response_model=WordResult)
async def get_word(word: str):
    user_id = "test"
    lang = 'IT'
    word_result = db_service.get_word(user_id, lang, word)
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
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

@app.post("/describe-word", response_model=WordResult)
async def describe_word(req: DescriptionRequest):
    result = bedrock_service.describe_word(req.description)
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
