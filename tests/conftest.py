import pytest

from lb.schema import word_count


def forms(en="The capital of Australia is Canberra.", hi="ऑस्ट्रेलिया की राजधानी कैनबरा है।",
          hi_rom="Australia ki rajdhani Canberra hai.", hinglish="Australia ki capital Canberra hai."):
    return {f: {"text": t, "words": word_count(t)}
            for f, t in (("en", en), ("hi", hi), ("hi_rom", hi_rom), ("hinglish", hinglish))}


@pytest.fixture
def quad_record():
    return {
        "item_id": "mmmlu-geo-0042", "source": "MMMLU", "subject": "geography", "type": "factual",
        "question_en": "What is the capital of Australia?", "reference_en": "Canberra.",
        "answers": forms(), "wrong": None, "drafted_by": "claude-opus-5-5",
        "qc": {"verified_by": [], "verified_on": None, "edits": 0, "passed": False, "notes": ""},
        "pilot": True,
    }


class FakeProvider:
    """Counts calls and returns scripted responses in order."""
    name = "fake"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.prompts = []

    def complete(self, prompt, temperature=0.0):
        from lb.providers import Completion
        self.calls += 1
        self.prompts.append(prompt)
        return Completion(text=self.responses.pop(0), tokens={"prompt": 1, "completion": 1})
