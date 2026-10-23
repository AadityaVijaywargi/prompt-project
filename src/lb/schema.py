"""Pydantic models for every JSONL / CSV record in the project (brief section 4)."""
from __future__ import annotations

import unicodedata
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Form = Literal["en", "hi", "hi_rom", "hinglish"]
FORMS: tuple[str, ...] = ("en", "hi", "hi_rom", "hinglish")
ItemType = Literal["factual", "open_ended"]


def word_count(text: str) -> int:
    return len(text.split())


def is_nfc(text: str) -> bool:
    return unicodedata.is_normalized("NFC", text)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- data/questions.jsonl ----------

class Question(Strict):
    item_id: str
    source: Literal["MMMLU", "MT-Bench", "MT-Bench-Hi"]
    source_id: str                     # e.g. "astronomy/12" (MMLU subject/index) or MT-Bench question_id
    subject: str
    domain: Literal["stem", "humanities", "open_ended"]
    type: ItemType
    question_en: str
    question_hi_source: Optional[str] = None   # official MMMLU Hindi question text, kept for reference
    choices_en: Optional[list[str]] = None
    answer_letter: Optional[Literal["A", "B", "C", "D"]] = None


# ---------- data/quadruples.jsonl ----------

class AnswerText(Strict):
    text: str = Field(min_length=1)
    words: int = Field(ge=1)

    @model_validator(mode="after")
    def _check(self) -> "AnswerText":
        if not is_nfc(self.text):
            raise ValueError("text is not NFC-normalized")
        if self.words != word_count(self.text):
            raise ValueError(f"words={self.words} but text has {word_count(self.text)} words")
        return self


class FourForms(Strict):
    en: AnswerText
    hi: AnswerText
    hi_rom: AnswerText
    hinglish: AnswerText

    def get(self, form: str) -> AnswerText:
        return getattr(self, form)


class QC(Strict):
    verified_by: list[str] = Field(default_factory=list)
    verified_on: Optional[date] = None
    edits: int = 0
    passed: bool = False
    notes: str = ""

    @model_validator(mode="after")
    def _passed_needs_verifier(self) -> "QC":
        if self.passed and (not self.verified_by or self.verified_on is None):
            raise ValueError("qc.passed=true requires verified_by and verified_on")
        return self


class Quadruple(Strict):
    item_id: str
    source: Literal["MMMLU", "MT-Bench", "MT-Bench-Hi"]
    subject: str
    type: ItemType
    question_en: str
    reference_en: Optional[str] = None
    answers: FourForms
    wrong: Optional[FourForms] = None
    drafted_by: str
    qc: QC                              # covers question_en and answers
    wrong_qc: Optional[QC] = None       # covers the wrong twin separately (E3 uses it only when passed)
    pilot: bool = False

    @field_validator("question_en")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("empty question")
        return v

    @model_validator(mode="after")
    def _wrong_has_qc(self) -> "Quadruple":
        if (self.wrong is None) != (self.wrong_qc is None):
            raise ValueError("wrong and wrong_qc must be present together")
        if self.wrong is not None and self.type != "factual":
            raise ValueError("wrong twins are for factual items only")
        return self

    @property
    def wrong_usable(self) -> bool:
        return self.wrong is not None and self.wrong_qc is not None and self.wrong_qc.passed


# ---------- judge outputs ----------

class PointwiseScore(Strict):
    correctness: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    language_quality: int = Field(ge=1, le=5)
    comment: str = ""

    @property
    def content(self) -> float:
        return (self.correctness + self.completeness + self.clarity) / 3

    @property
    def overall(self) -> float:
        return (self.correctness + self.completeness + self.clarity + self.language_quality) / 4


class PairwiseVerdict(Strict):
    winner: Literal["A", "B", "tie"]
    reason: str = ""


# ---------- results/raw/*.jsonl ----------

class RawCall(Strict):
    run_id: str
    experiment: str
    judge: str
    model: str
    provider: str
    prompt_variant: str
    item_id: str
    forms: list[str]
    order: Optional[Literal["AB", "BA"]] = None
    attempt: int
    raw_response: Optional[str]
    parsed: Optional[dict]
    parse_ok: bool
    error: Optional[str] = None
    tokens: dict = Field(default_factory=dict)
    timestamp: str
    cache_hit: bool
    cache_key: str


# ---------- data/human_grades.csv ----------

class HumanGrade(Strict):
    annotator_id: str
    item_id: str
    form: Form
    correctness: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    language_quality: int = Field(ge=1, le=5)
    notes: str = ""
