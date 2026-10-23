# Data plan

## Sources

| Source | What we take | How |
|---|---|---|
| MMMLU (`openai/MMMLU`, HI_IN test) + MMLU (`cais/mmlu` test) | Factual MCQ stems, options, answer key; official Hindi question kept as `question_hi_source` | `scripts/fetch_sources.py`. Rows matched by (subject, index); the script checks subject, index and answer letter agree |
| MT-Bench (`HuggingFaceH4/mt_bench_prompts`) | Open-ended first-turn prompts | same script. `source_id` is that dataset's `prompt_id` |
| MT-Bench-Hi (Kamath et al., arXiv:2508.19831) | Planned for Phase 1 open-ended items | not fetched yet |

Candidate sampling: `candidates_per_subject` random indices per subject, seed `20261023` (experiments.yaml),
14 subjects (7 STEM, 7 humanities) = 56 candidates in `data/sources/mmmlu_candidates.jsonl`.

## Selection rule for factual items

Keep a candidate only if (1) the keyed answer is correct and can be explained in 2-4 sentences without a
long calculation, (2) the stem does not depend on a quoted passage, (3) the key is not "All of the above"
or "both a and b", and (4) the item is not a narrow reading of a single author that we cannot verify.

### Pilot (Phase 0): 20 items = 15 MMMLU factual + 5 MT-Bench open-ended

Kept (15 factual): astronomy/136, astronomy/67, high_school_biology/123, high_school_biology/293,
high_school_chemistry/5, anatomy/66, computer_security/2, conceptual_physics/202,
high_school_geography/66, world_religions/95, world_religions/145, high_school_government_and_politics/135,
high_school_government_and_politics/82, international_law/38, prehistory/78.

Excluded candidates and reason:

| Candidate | Reason |
|---|---|
| high_school_world_history/13, /72, /74, /188 | passage-based stems (rule 2) |
| virology/37, /96 | key is "All of the above" (rule 3) |
| philosophy/296 | key is "both a and b" (rule 3) |
| computer_security/18 | weak key ("escape queries"; parameterised queries are the standard answer) (rule 1) |
| world_religions/84 | dubious key: *samyak jnana* is usually "right knowledge", not "intuition" (rule 1) |
| virology/152 | dubious key ("chemotherapy" for herpes control) (rule 1) |
| astronomy/51, high_school_chemistry/19 | needs a multi-step calculation (rule 1) |
| philosophy/122, /257, /265, world_religions/10, prehistory/139 | narrow author / specialist reading (rule 4) |
| remaining candidates | valid but not needed for 15; available for Phase 1 |

Open-ended (5): MT-Bench prompt ids 57239570 (stem), 80635012 (stem), 97392077 (humanities),
36620167 (humanities), 15896981 (reasoning). Chosen to be answerable in about 50-110 words; coding, maths
and long creative-writing prompts left out of the pilot.

## Drafting and verification

- All four forms are drafted by **claude-opus-5-5** (`drafted_by`). It is not, and must not be, a judge.
  `data_check` and `build_judges` both enforce this.
- Drafts live in `data/drafts/pilot_v1.yaml` (human-readable). `scripts/build_pilot.py` builds
  `data/quadruples.jsonl` with computed word counts and NFC text.
- Hindi-fluent checkers verify via `make qc-export` → edit `data/qc/to_verify.csv` → `make qc-import`.
  An item enters analysis only when all its non-English rows are marked `ok=Y` with a verifier name.
- Points for the checkers to watch:
  - hi_rom keeps standard Hindi loanwords for technical terms (DNA, allele, server, ticket, card) because
    pure-Hindi coinages would be unnatural. Flag any you would write differently.
  - Spelling of Romanized Hindi is informal and without diacritics (rajdhani, not rājdhānī).
  - Legal / biology terms in hi follow NCERT-style Hindi where we know it (उत्प्रेषण रिट, अनुलेखन);
    please correct if a more standard term exists.

## Wrong twins (Phase 1)

About 60 factual items get a plausible but wrong English answer of similar length, plus the same wrong
answer in the other three forms, stored in `quadruples.jsonl` under `wrong` and verified the same way.

## Pilot length check

Word ratio vs English across the 20 pilot items (computed by `make data-check` inputs): hi 0.93-1.35
(median 1.15), hi_rom 0.93-1.35 (median 1.15), hinglish 0.95-1.23 (median 1.13). All inside 0.6-1.8.
