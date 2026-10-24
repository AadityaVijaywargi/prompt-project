# Analysis plan (fixed before any results are inspected)

Status: **v1, written 2026-10-23, before any judge call.** No judge outputs exist yet. Changes after the
first results are seen must be logged at the bottom with a date and a reason, and reported as post hoc.

Scope: only items with `qc.passed = true`. Pilot runs (Phase 0) are labelled **pilot** everywhere and are
not pooled with main results. 95% confidence intervals everywhere. Any cell with fewer than 30 paired items
is labelled **exploratory**.

## Notation

- Forms: `en`, `hi`, `hi_rom`, `hinglish`. Judges: the enabled panel in `configs/judges.yaml`.
- Content score = mean(correctness, completeness, clarity). Overall = mean of all four criteria.
- A judge call whose response fails to parse after 2 retries is **missing**; the item is dropped from that
  comparison only, and missing counts are reported per judge and form.

## E1: pointwise gap (RQ1, RQ3)

Per judge `j`, per item `i`: `d_i = score_j(i, form) - score_j(i, en)`.

| ID | Comparison | Measure |
|---|---|---|
| E1.1 | hi vs en | content score (primary), overall (secondary) |
| E1.2 | hi_rom vs en | content (primary), overall |
| E1.3 | hinglish vs en | content (primary), overall |
| E1.4 | hi vs hi_rom (script contrast, RQ3) | content |
| E1.5 | hi_rom vs hinglish (mixing contrast, RQ3) | content |

- Report mean `d` with a paired bootstrap 95% CI (10,000 resamples over items, seed 20261023), and a
  two-sided Wilcoxon signed-rank p-value. Two-sided: we do not assume Hindi scores lower.
- Holm correction within each judge across the 5 primary (content) comparisons E1.1-E1.5.
- Verbosity control: OLS of `d` on `log(words_form / words_en)` per judge and comparison; report slope,
  its p-value, and the intercept (gap at equal length).
- Split by item type (factual / open_ended) as a secondary, exploratory table.
- Per-criterion gaps (including language_quality alone) reported descriptively.

## E2: pairwise preference (RQ2)

Pairs en-hi, en-hi_rom, en-hinglish, each run in both orders (AB, BA).

| ID | Measure | Method |
|---|---|---|
| E2.1 | English win-rate = en wins / (en wins + en losses), counting each order as one judgment | binomial test vs 0.5, Wilson CI |
| E2.2 | Tie rate | proportion with Wilson CI, reported separately |
| E2.3 | Position consistency = share of (item, pair) where the same underlying answer wins (or tie) in both orders | proportion with Wilson CI |
| E2.4 | A-slot rate = share of non-tie judgments won by whichever answer is in slot A | proportion with Wilson CI |
| E2.5 | Order-consistent English win-rate: only (item, pair) cells with a consistent non-tie verdict | Wilson CI |

Holm correction across the 3 pairs per judge for E2.1.

## E3: wrong English vs correct non-English (RQ2)

| ID | Measure | Method |
|---|---|---|
| E3.1 | Any-order wrong-English rate: share of (item, form) where wrong en wins in at least one order | Wilson CI per judge and form |
| E3.2 | Consistent wrong-English rate: wrong en wins in both orders | Wilson CI per judge and form |
| E3.3 | Control: wrong en vs correct en, same two rates | Wilson CI; expected near 0 |

## E4: human agreement (RQ4)

1. Inter-annotator agreement first (the ceiling): quadratic-weighted Cohen's kappa per criterion and per
   form, for each annotator pair; bootstrap CI over items.
2. Judge vs mean human score per form: Spearman correlation on the content score and quadratic-weighted
   kappa on rounded scores (round half up), bootstrap 95% CI over items.
3. Per-form comparison of judge-human agreement (does agreement drop for hi / hi_rom / hinglish?).

## E5: mitigations (RQ5)

For each variant (hindi_rubric, translate_then_judge, bias_aware, majority_vote) on the E5 subset, paired
by item against the baseline run on the same items and judges:

- Change in E1 gap (signed and absolute), bootstrap CI of the paired change.
- Change in E2 English win-rate and in E3 consistent wrong-English rate, with CIs.
- Accuracy cost: change in E4 judge-human agreement and in E3 control accuracy (correct en preferred).
- Report effect sizes with CIs; p-values secondary.

## App thresholds

`results/thresholds.json`: per judge, the 95th percentile of `|content(form) - content(en)|` across all
matched (item, form) pairs from the baseline E1 run.

## Change log

- **2026-10-24, judge panel (model availability, no comparison changed).**
  - `gemini-flash`: model `gemini-2.5-flash` -> `gemini-3.5-flash`. 2.5 returned 404 "no longer available to
    new users" on the first call; `gemini-3.8-flash` answered but took 85-182 s per call on the free tier.
    18 pilot E1 calls exist, all on 3.5. Google's quota error attributes these calls to `gemini-3.6-flash`.
  - `llama-3.3-70b` replaced by `gpt-oss-120b` (`openai/gpt-oss-120b` on Groq), also as the E5(b)
    translator. `llama-3.3-70b-versatile` returned 404 model_not_found (decommissioned) on its first call, so
    no Llama output exists. `qwen/qwen3.8-27b` was not chosen: preview status, and the same family as the local
    Qwen judge.
  - Both changes were made before any analysis was run, so no result is affected.
- **2026-10-24, main-study judges actually run (feasibility, no comparison changed).**
  - E1-E3 baseline judges: `qwen2.5-7b-local` (complete: 1,980 calls, split across 4 laptops with
    `--shard K/4`) and `gpt-oss-120b` (Groq free tier, same 4-way split, each team member on their own free
    key). `gemini-flash` stays in `configs/experiments.yaml` but is pilot-only for now: Google's free tier
    allows 20 requests/day per key, so 1,980 calls do not fit the project timeline without billing.
  - Not used: Claude models (paid API only, and the same family as the drafting model, i.e. the
    self-preference risk the drafter guard exists for); a second Ollama model (feasible, but another 7-9B
    judge cannot test whether the effects hold for a large judge).
  - Timing: decided after the Qwen E1-E3 tables were generated (commit fc41489). The judge was chosen for
    availability, cost and size; no result was used to choose it, and no analysis in this plan changes.
  - The 200 pilot `gpt-oss-120b` calls (20 items, E1 + E2) are byte-identical requests to the matching
    main-study calls, so the main run takes them from the cache instead of sending them again. Pilot
    run records themselves stay excluded from main tables (`lb.analysis` and `scripts/check_shard.py`
    skip `pilot-` runs); the main run logs its own records for those calls.
