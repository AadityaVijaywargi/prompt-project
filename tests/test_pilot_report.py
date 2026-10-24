import json
from pathlib import Path
import pytest
from scripts.pilot_report import generate_pilot_report


def test_pilot_report_synthetic(tmp_path):
    raw_dir = tmp_path / "raw"
    tables_dir = tmp_path / "tables"
    report_file = tmp_path / "pilot_report.md"
    raw_dir.mkdir(parents=True)
    tables_dir.mkdir(parents=True)

    # Synthetic E1 data
    e1_calls = [
        {"experiment": "e1", "prompt_variant": "baseline", "judge": "judge-a", "item_id": "test-1", "forms": ["en"],
         "parsed": {"correctness": 5, "completeness": 5, "clarity": 5, "language_quality": 5},
         "parse_ok": True, "attempt": 0},
        {"experiment": "e1", "prompt_variant": "baseline", "judge": "judge-a", "item_id": "test-1", "forms": ["hi"],
         "parsed": {"correctness": 4, "completeness": 4, "clarity": 4, "language_quality": 4},
         "parse_ok": True, "attempt": 0},
        {"experiment": "e1", "prompt_variant": "baseline", "judge": "judge-a", "item_id": "test-1", "forms": ["hi_rom"],
         "parsed": {"correctness": 4, "completeness": 4, "clarity": 4, "language_quality": 4},
         "parse_ok": True, "attempt": 0},
        {"experiment": "e1", "prompt_variant": "baseline", "judge": "judge-a", "item_id": "test-1", "forms": ["hinglish"],
         "parsed": {"correctness": 5, "completeness": 4, "clarity": 5, "language_quality": 5},
         "parse_ok": True, "attempt": 0},
    ]

    # Synthetic E2 data
    e2_calls = [
        {"experiment": "e2", "prompt_variant": "baseline", "judge": "judge-a", "item_id": "test-1", "forms": ["en", "hi"],
         "order": "AB", "parsed": {"winner": "A", "reason": "English was clearer."},
         "parse_ok": True, "attempt": 0},
        {"experiment": "e2", "prompt_variant": "baseline", "judge": "judge-a", "item_id": "test-1", "forms": ["en", "hi"],
         "order": "BA", "parsed": {"winner": "B", "reason": "English was clearer."},
         "parse_ok": True, "attempt": 0},
    ]

    with open(raw_dir / "e1__pilot-synthetic.jsonl", "w", encoding="utf-8") as f:
        for r in e1_calls:
            f.write(json.dumps(r) + "\n")

    with open(raw_dir / "e2__pilot-synthetic.jsonl", "w", encoding="utf-8") as f:
        for r in e2_calls:
            f.write(json.dumps(r) + "\n")

    e1_rows, e2_rows = generate_pilot_report(raw_dir=raw_dir, tables_dir=tables_dir, report_path=report_file)

    assert len(e1_rows) == 8  # 5 primary content + 3 overall
    assert len(e2_rows) == 1  # 1 pair

    assert (tables_dir / "pilot_e1_pointwise.csv").exists()
    assert (tables_dir / "pilot_e2_pairwise.csv").exists()
    assert report_file.exists()

    content = report_file.read_text(encoding="utf-8")
    assert "PILOT and exploratory" in content
    assert "judge-a" in content


def test_pilot_report_filters_by_variant(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    def e2_call(variant, order, winner):
        return {"experiment": "e2", "prompt_variant": variant, "judge": "judge-a", "item_id": "test-1",
                "forms": ["en", "hi"], "order": order, "parsed": {"winner": winner, "reason": "x"},
                "parse_ok": True, "attempt": 0}

    # Baseline: English wins in both orders. Bias-aware: Hindi wins in both orders.
    # bias_aware sorts after baseline, so without filtering it would overwrite baseline.
    runs = {
        "e2__pilot-baseline-1.jsonl": [e2_call("baseline", "AB", "A"), e2_call("baseline", "BA", "B")],
        "e2__pilot-bias_aware-1.jsonl": [e2_call("bias_aware", "AB", "B"), e2_call("bias_aware", "BA", "A")],
    }
    for name, calls in runs.items():
        with open(raw_dir / name, "w", encoding="utf-8") as f:
            for r in calls:
                f.write(json.dumps(r) + "\n")

    report_file = tmp_path / "pilot_report.md"
    _, e2_rows = generate_pilot_report(raw_dir=raw_dir, tables_dir=tmp_path / "tables", report_path=report_file)
    assert (e2_rows[0]["en_wins"], e2_rows[0]["form_wins"]) == (2, 0)
    assert "Prompt variant: `baseline`" in report_file.read_text(encoding="utf-8")

    _, e2_rows = generate_pilot_report(raw_dir=raw_dir, tables_dir=tmp_path / "tables", report_path=report_file,
                                       variant="bias_aware")
    assert (e2_rows[0]["en_wins"], e2_rows[0]["form_wins"]) == (0, 2)
    assert "Prompt variant: `bias_aware`" in report_file.read_text(encoding="utf-8")
