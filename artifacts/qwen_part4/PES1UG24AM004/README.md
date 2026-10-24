# Submission Package: Qwen Part 4 of 4 (PES1UG24AM004)

## 1. Submission Identification
- **Student / Submission ID:** `PES1UG24AM004`
- **Repository:** `AadityaVijaywargi/prompt-project`
- **Experiment:** Local Qwen Baseline (Part 4 of 4)
- **Judge:** `qwen2.5-7b-local`
- **Ollama Model:** `qwen2.5:7b-instruct` (Model ID: `845dbda0ea48`)
- **Shard:** `4/4`

---

## 2. Verified Execution Summary
The local Qwen baseline run for Part 4 of 4 executed all 498 planned calls with **zero missing calls**.

| Experiment | Description | Planned Calls | Parsed Successfully | Unparsed Failures | Missing Calls | Status |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
| **E1** | Pointwise Scoring | 148 | 148 | 0 | 0 | **COMPLETE** |
| **E2** | Pairwise Comparison | 222 | 222 | 0 | 0 | **COMPLETE** |
| **E3** | Wrong-Answer Comparison & Control | 128 | 125 | 3 | 0 | **COMPLETE** |
| **Total** | **All Part 4 Runs** | **498** | **495** | **3** | **0** | **COMPLETE** |

### Shard Checker Status
Confirmed directly via repository checker (`scripts/check_shard.py --judge qwen2.5-7b-local --shard 4/4`):
```text
qwen2.5-7b-local, baseline, shard 4/4
  e1: planned 148, parsed OK 148, unparsed after retries 0, missing 0
  e2: planned 222, parsed OK 222, unparsed after retries 0, missing 0
  e3: planned 128, parsed OK 125, unparsed after retries 3, missing 0
COMPLETE
```

---

## 3. Existing Experiment Commits on `main`
The experiment results were previously committed and pushed directly to `origin/main` in dedicated, results-only commits:

1. **E1 Baseline:** Commit [`c2901470a2db2ea85042085dfbe6e28422815be1`](https://github.com/AadityaVijaywargi/prompt-project/commit/c2901470a2db2ea85042085dfbe6e28422815be1)
   - Message: `qwen part 4/4: e1 baseline`
   - Added: `results/raw/e1__baseline-shard4of4-20261024T123727.jsonl` + 148 cache entries
2. **E2 Baseline:** Commit [`1c8f7477ef758806d9069e83535bdb907cccd675`](https://github.com/AadityaVijaywargi/prompt-project/commit/1c8f7477ef758806d9069e83535bdb907cccd675)
   - Message: `qwen part 4/4: e2 baseline`
   - Added: `results/raw/e2__baseline-shard4of4-20261024T132327.jsonl` + 222 cache entries
3. **E3 Baseline:** Commit [`ccbab19970deb47cf8b637b186908febb595fcab`](https://github.com/AadityaVijaywargi/prompt-project/commit/ccbab19970deb47cf8b637b186908febb595fcab)
   - Message: `qwen part 4/4: e3 baseline`
   - Added: `results/raw/e3__baseline-shard4of4-20261024T141633.jsonl` + 134 cache entries

All three commits are verified ancestors of current `origin/main`.

---

## 4. Submission Package Contents
This directory (`artifacts/qwen_part4/PES1UG24AM004/`) packages the complete documentation, execution logs, and portable backup for evaluation:

- `README.md`: This submission manifest and metadata file.
- `qwen_part4_run_report.txt`: Sanitized initial execution report documenting environment configuration, test validation (58/58 pytest passed, 150 qc.passed items), execution duration (2h 7m 4s), and call statistics.
- `qwen_part4_final_report.txt`: Sanitized comprehensive independent audit report confirming Git ancestry, results scoping, process cleanup, and filesystem boundaries.
- `qwen_part4_results.zip`: Audited 507-member ZIP archive containing all 3 raw JSONL files and 504 cache JSON files for Part 4/4 (`testzip()` integrity verified).
- `logs/e1_pointwise.log`: Real-time execution log for E1 (148 calls done, 0 unparsed, `{'ok': 148, 'failed': 0}`).
- `logs/e2_pairwise.log`: Real-time execution log for E2 (222 calls done, 0 unparsed, `{'ok': 222, 'failed': 0}`).
- `logs/e3_wrong.log`: Real-time execution log for E3 (128 calls done, 3 unparsed, `{'ok': 125, 'failed': 3}`).

*Note: Machine-specific absolute directory paths have been replaced with neutral placeholders (`<LOCAL_WORKSPACE>`, `<REPO_ROOT>`) in submitted text reports to prevent leaking local environment specifics.*

---

## 5. Important Research Caveat: E3 Unparsed Calls
In accordance with project protocol:
- In E3, exactly **3 judging calls** remained unparseable after the maximum permitted automated retries.
- These 3 calls are recorded failures in `results/raw/e3__baseline-shard4of4-20261024T141633.jsonl`, **not missing gaps**.
- They are accurately disclosed as unparsed failures (`failed: 3`) and must **not** be misrepresented as successfully parsed responses. Full coverage of the assigned 128 calls is complete.

---

## 6. Data-Handling Note
Individual raw result files and granular cache entries already reside directly in the repository's `results/raw/` and `results/cache/` trees on `main`. The included `qwen_part4_results.zip` serves as an offline, portable archive containing the complete Part 4 raw outputs and referenced cache entries.
