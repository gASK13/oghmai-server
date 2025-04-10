from fastapi import FastAPI, HTTPException
from mangum import Mangum
import boto3
from models import *
import bedrock_service
import db_service

app = FastAPI()
handler = Mangum(app)
client = boto3.client("bedrock-runtime", region_name="us-east-1")

@app.get("/test")
async def test():
    return {"message": "Hello from FastAPI!"}

@app.post("/describe-word", response_model=WordResult)
async def describe_word(req: DescriptionRequest):
    try:
        result = bedrock_service.describe_word(req.description)
        return result

    except Exception as e:
        print(f"Error during describe_word: {e}")
        # print stacktrace
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/save-word")
async def save_word(word_result: WordResult):
    try:
        user_id = "test"  # For now hardcoded
        result = db_service.save_word(user_id, word_result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
