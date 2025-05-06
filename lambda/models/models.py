from pydantic import BaseModel
from typing import Optional
from enum import Enum
from datetime import datetime

class TestChallenge(BaseModel):
    description: str
    id: str

class DescriptionRequest(BaseModel):
    description: str
    exclusions: list[str] = None

class StatusEnum(str, Enum):  # Define the Enum for status
    UNSAVED = "UNSAVED"
    NEW = "NEW"
    LEARNED = "LEARNED"
    KNOWN = "KNOWN"
    MASTERED = "MASTERED"

    def raise_level(self):
        levels = list(StatusEnum)
        current_index = levels.index(self)
        if current_index < len(levels) - 1:
            return levels[current_index + 1]
        return self  # Already at the highest level

    def lower_level(self):
        levels = list(StatusEnum)
        current_index = levels.index(self)
        if current_index > 1: #NEW is lowest
            return levels[current_index - 1]
        return self

class WordActionEnum(str, Enum):
    UNDELETE = "UNDELETE"
    RESET = "RESET"

class ResultEnum(str, Enum):  # Define an Enum for the result
    INCORRECT = "INCORRECT"
    CORRECT = "CORRECT"
    PARTIAL = "PARTIAL"

class TestResult(BaseModel):
    result: ResultEnum
    suggestion: Optional[str] = None
    word: Optional[str] = None
    newStatus: Optional[StatusEnum] = None
    oldStatus: Optional[StatusEnum] = None

class TestStatistics(BaseModel):
    available: dict[StatusEnum, int] = {s: 0 for s in StatusEnum}   # Map StatusEnum to integer counts

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

class WordItem(BaseModel):
    word: str
    status: StatusEnum
    testResults: list[bool]

class WordList(BaseModel):
    words: list[WordItem]
