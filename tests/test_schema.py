import unicodedata

import pytest
from pydantic import ValidationError

from lb.schema import Quadruple


def test_valid_record(quad_record):
    q = Quadruple.model_validate(quad_record)
    assert q.answers.get("hi").text.startswith("ऑस्ट्रेलिया")


def test_wrong_word_count_rejected(quad_record):
    quad_record["answers"]["en"]["words"] += 1
    with pytest.raises(ValidationError, match="words="):
        Quadruple.model_validate(quad_record)


def test_non_nfc_rejected(quad_record):
    # Precomposed nukta letters (U+0958 क़) are composition exclusions: NFC decomposes them.
    precomposed = "क़िला है।"
    assert precomposed != unicodedata.normalize("NFC", precomposed)
    quad_record["answers"]["hi"] = {"text": precomposed, "words": 2}
    with pytest.raises(ValidationError, match="NFC"):
        Quadruple.model_validate(quad_record)


def test_missing_form_rejected(quad_record):
    del quad_record["answers"]["hinglish"]
    with pytest.raises(ValidationError):
        Quadruple.model_validate(quad_record)


def test_passed_requires_verifier(quad_record):
    quad_record["qc"]["passed"] = True
    with pytest.raises(ValidationError, match="verified_by"):
        Quadruple.model_validate(quad_record)
    quad_record["qc"].update(verified_by=["a1"], verified_on="2026-10-30")
    assert Quadruple.model_validate(quad_record).qc.passed


def test_unknown_field_rejected(quad_record):
    quad_record["surprise"] = 1
    with pytest.raises(ValidationError):
        Quadruple.model_validate(quad_record)
