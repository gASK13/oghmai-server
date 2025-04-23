from pydantic import BaseModel
from typing import Optional
from enum import Enum
from datetime import datetime

class DescriptionRequest(BaseModel):
    description: str
    exclusions: list[str] = None

class StatusEnum(str, Enum):  # Define the Enum for status
    UNSAVED = "UNSAVED"
    NEW = "NEW"
    LEARNED = "LEARNED"
    KNOWN = "KNOWN"
    MASTERED = "MASTERED"

class WordResult(BaseModel):
    word: str
    translation: str
    definition: str
    examples: list[str]
    language: str = "IT"  # Default to IT for now
    createdAt: Optional[datetime] = None
    status: StatusEnum = StatusEnum.UNSAVED
    lastTest: Optional[datetime] = None
    testResults: Optional[list[bool]] = None

class WordList(BaseModel):
    words: list[str]
