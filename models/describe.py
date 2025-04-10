from pydantic import BaseModel

class DescriptionRequest(BaseModel):
    description: str

class WordResult(BaseModel):
    word: str
    translation: str
    definition: str
    examples: list[str]