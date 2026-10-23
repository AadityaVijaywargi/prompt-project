"""Prompt rendering. Placeholders are filled by exact replacement so JSON braces in prompts survive."""
from __future__ import annotations

from functools import lru_cache

from .config import PROMPTS

REFERENCE_LABEL = {"en": "Reference answer", "hi": "संदर्भ उत्तर"}


@lru_cache(maxsize=None)
def load(name: str) -> str:
    return (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")


def fill(template: str, **values: str) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out


def _reference_block(prompt_name: str, reference: str | None) -> str:
    if not reference:
        return ""
    lang = "hi" if prompt_name.endswith("_hi") else "en"
    return f"{REFERENCE_LABEL[lang]}: {reference}\n"


def _with_suffix(text: str, suffix: str | None) -> str:
    return text if not suffix else text.rstrip("\n") + "\n\n" + load(suffix).strip() + "\n"


def render_pointwise(prompt_name: str, question: str, answer: str,
                     reference: str | None = None, suffix: str | None = None) -> str:
    text = fill(load(prompt_name), question=question, answer=answer,
                reference_block=_reference_block(prompt_name, reference))
    return _with_suffix(text, suffix)


def render_pairwise(prompt_name: str, question: str, answer_a: str, answer_b: str,
                    reference: str | None = None, suffix: str | None = None) -> str:
    text = fill(load(prompt_name), question=question, answer_a=answer_a, answer_b=answer_b,
                reference_block=_reference_block(prompt_name, reference))
    return _with_suffix(text, suffix)


def render_translation(text: str) -> str:
    return fill(load("translate_to_en"), text=text)
