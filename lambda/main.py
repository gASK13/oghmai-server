from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from mangum import Mangum
import boto3
from models import *
import bedrock_service
import db_service
import logging

app = FastAPI()
handler = Mangum(app)
client = boto3.client("bedrock-runtime", region_name="us-east-1")

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


@app.get("/test")
async def test():
    return {"message": "Hello from FastAPI!"}

@app.post("/describe-word", response_model=WordResult)
async def describe_word(req: DescriptionRequest):
    result = bedrock_service.describe_word(req.description)
    return result

@app.post("/save-word")
async def save_word(word_result: WordResult):
    user_id = "test"  # For now hardcoded
    result = db_service.save_word(user_id, word_result)
    return result
