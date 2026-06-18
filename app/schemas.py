"""
schemas.py — Pydantic models for /chat request and response.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class Message(BaseModel):
    role: str        # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]


class Recommendation(BaseModel):
    name: str        # Assessment name from the catalog
    url: str         # Direct catalog URL (maps to 'link' in catalog)
    test_type: str   # Type code(s) (maps to 'keys' in catalog, e.g. "Personality & Behavior")
    job_levels: List[str] = Field(default_factory=list) # Target seniority
    languages: List[str] = Field(default_factory=list)  # Available languages
    reason: Optional[str] = None # Agent's reasoning


class ChatResponse(BaseModel):
    reply: str                              # Agent's natural language response
    recommendations: List[Recommendation]  # Empty [] while clarifying; 1-10 items when recommending
    end_of_conversation: bool               # True only when task is complete

class AssessmentDetail(BaseModel):
    name: str
    url: str
    test_types: List[str]
    description: str
    duration: Optional[int]
    remote_support: bool
    adaptive_support: bool

class RoleTemplate(BaseModel):
    role: str
    seniority: str
    description: str
    recommended_assessments: List[str]
