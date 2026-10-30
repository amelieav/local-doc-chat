"""Data models for ingested documents."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePath
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class DocumentStatus(StrEnum):
    """Whether a document has text we can search."""

    READY = "ready"
    NO_TEXT = "no_text"


class Page(BaseModel):
    """The extracted text of one PDF page. Page numbers start at 1."""

    model_config = ConfigDict(frozen=True)

    document_id: UUID
    page_number: int = Field(ge=1)
    text: str


class Word(BaseModel):
    """A word and its box in PDF points, measured from the top-left of the page."""

    model_config = ConfigDict(frozen=True)

    text: str
    x0: float
    top: float
    x1: float
    bottom: float


class ExtractedPage(BaseModel):
    """What the extractor reads from one page, before it is tied to a document."""

    model_config = ConfigDict(frozen=True)

    page_number: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    text: str
    words: tuple[Word, ...]


class Document(BaseModel):
    """An uploaded PDF and its metadata."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    filename: str = Field(min_length=1, max_length=255)
    sha256: Sha256
    size_bytes: int = Field(gt=0)
    page_count: int = Field(ge=1)
    status: DocumentStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("filename")
    @classmethod
    def strip_directories(cls, value: str) -> str:
        """Keep only the final path component, from either Windows or POSIX paths."""
        name = PurePath(value.replace("\\", "/")).name
        if name in {"", ".", ".."}:
            msg = "filename must not be empty"
            raise ValueError(msg)
        return name
