from fastapi import FastAPI, HTTPException
from mangum import Mangum
import boto3
from models import *
from bedrock_service import *

app = FastAPI()
handler = Mangum(app)
client = boto3.client("bedrock-runtime", region_name="us-east-1")

@app.get("/test")
async def test():
    return {"message": "Hello from FastAPI!"}

@app.post("/describe-word", response_model=WordResult)
async def describe_word(req: DescriptionRequest):
    try:
        result = bedrock_describe_word("Describe the word 'pomodoro' in Italian.")
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
