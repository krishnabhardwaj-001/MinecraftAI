
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class Detail(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    value: str
    description: Optional[str] = None


class Requirement(BaseModel):
    model_config = ConfigDict(extra="allow")

    subject: Optional[str] = None
    target: Optional[str] = None
    intent: str

    details: List[Detail] = Field(default_factory=list)
    conditions: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)

    description: Optional[str] = None


class Clarification(BaseModel):
    model_config = ConfigDict(extra="allow")

    reason: str
    question: str
    options: List[str] = Field(default_factory=list)


class MinecraftUnderstandingResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str

    minecraft_version: str = "1.21.11"
    edition: str = "Java"

    understood_request: str

    requirements: List[Requirement] = Field(
        default_factory=list
    )

    clarification: Optional[Clarification] = None

    missing_information: List[str] = Field(
        default_factory=list
    )

