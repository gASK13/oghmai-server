from pydantic import BaseModel

class DescriptionRequest(BaseModel):
    description: str
    exclusions: list[str] = None

class WordResult(BaseModel):
    word: str
    translation: str
    definition: str
    examples: list[str]
    language: str = "IT"  # Default to IT for now

class WordList(BaseModel):
    words: list[str]