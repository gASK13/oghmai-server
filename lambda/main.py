from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from mangum import Mangum

app = FastAPI()
handler = Mangum(app)

class DescriptionRequest(BaseModel):
    description: str

class WordResult(BaseModel):
    word: str
    translation: str
    definition: str
    examples: list[str]

@app.get("/test")
async def test():
    return {"message": "Hello from FastAPI!"}

@app.post("/guess-word", response_model=WordResult)
async def guess_word(req: DescriptionRequest):
    try:
        # In the future: Call Bedrock or any AI API here
        # For now, fake result based on simple matching
        # You can replace this with real logic later

        if "small round red fruit" in req.description.lower():
            result = WordResult(
                word="pomodoro",
                translation="tomato",
                definition="Un frutto rosso usato spesso nelle insalate o nei sughi.",
                examples=[
                    "Ho comprato un chilo di pomodori al mercato.",
                    "Il pomodoro è un ingrediente base della cucina italiana.",
                ],
            )
        else:
            result = WordResult(
                word="parola",
                translation="word",
                definition="Unità di significato linguistico.",
                examples=[
                    "Questa è una parola difficile da spiegare.",
                    "Le parole hanno un grande potere.",
                ],
            )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
