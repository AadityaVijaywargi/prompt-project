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

Implementation details (fixed 2026-10-27, before any E5 variant call; `lb.runners.e5_mitigation`, `lb.mitigation`):

- Subset: 60 items, stratified by type in proportion to the full set (40 factual, 20 open-ended), filled
  round-robin across subjects with seed 20261023. The factual picks are items with a verified wrong twin, so
  E3 runs on the subset's own 40 twins (the brief's 1,920 calls per variant assumed 60 twins; with the
  control added, a variant is 1,840 calls for 2 judges).
- E1: content gap vs en per form; change = variant minus baseline per item (signed, and of the absolute gap).
  E2: pooled English win-rate over non-tie judgments; change with an item bootstrap. E3: consistent
  wrong-English rate per form, and control accuracy (correct en wins in both orders); paired change per item.
- translate_then_judge: one translator, gpt-oss-120b at temperature 0 (`e5.translator`), translates the
  subset's hi, hi_rom and hinglish correct answers once (180 calls, logged as experiment `e5_translate`);
  English answers and the wrong English twin pass through. Judging waits until every translation exists.
- majority_vote: no calls. Median of each criterion (E1) and the majority slot verdict (E2, E3; a tie when
  no verdict has more than half) across the judges with complete baseline results, compared against each
  of those judges' baselines. With two judges the median is the mean and any disagreement is a tie.
- hindi_rubric runs only after a Hindi speaker verifies `pointwise_hi.txt` and `pairwise_hi.txt`.

## B: criterion leakage and judge comments (added 2026-10-26, post hoc; see change log)

Uses the E1 baseline records only, with no new judge calls. Per judge, per form `f` in hi, hi_rom, hinglish,
per item `i`, paired against en: `dC_i = correctness(f) - correctness(en)` and
`dL_i = language_quality(f) - language_quality(en)`. The content is identical across forms, so any `dC != 0`
is a bias; the question is whether it travels with the language_quality judgement.

| ID | Measure | Method |
|---|---|---|
| B1 | Leakage slope: OLS of `dC` on `dL` | slope with a percentile bootstrap 95% CI over items (10,000 resamples, seed 20261023) and the OLS p-value; Holm across the 3 forms per judge |
| B2 | Same slope for completeness and for clarity | bootstrap CI, descriptive |
| B3 | Mean `dC` split by the sign of `dL` (< 0, = 0, > 0) | bootstrap CI per cell, n per cell, descriptive |
| B4 | Language-mention rate: share of comments that mention language, script or code-mixing (lexicon below) | Wilson CI per judge and form; paired difference vs en with an exact McNemar test (binomial on discordant items); Holm across the 3 forms per judge |
| B5 | Silent penalty rate: among items with `content(f) < content(en)`, share whose `f` comment has no language, script or mixing mention | Wilson CI per judge and form |

- If `dL` has no variance for a judge and form, B1-B3 are reported as not estimable, not as zero.
- Comment lexicon, fixed before any comment was read: case-insensitive regular expressions in
  `src/lb/leakage.py` (`MENTION_PATTERNS`), in four categories. **language**: language, linguistic, Hindi,
  English, translat-, भाषा, हिंदी/हिन्दी, अंग्रेज़ी. **script**: script, Devanagari, Roman/romanized,
  transliterat-, लिपि, देवनागरी. **mixing**: Hinglish, code-mix(ed/ing), code-switch(ed/ing), mixed language,
  a mix of Hindi/English. **fluency** (reported separately, not part of B4/B5): fluent/fluency, grammar,
  spelling, informal, colloquial, awkward, unnatural, slang, व्याकरण.
- Coder check (two raters since 2026-10-27, see change log): a seeded random sample of 25 comments per judge
  and form goes to `results/tables/main_baseline_b_comment_sample.csv` with blank `rater_a`, `rater_b` and
  `adjudicated` columns and no automated label, so raters code blind. Two raters fill in 1/0 independently; a
  third person adjudicates disagreements. Agreed label = `adjudicated`, else the raters' label when they agree.
  Reported per judge and pooled: Cohen's kappa between raters (bootstrap 95% CI over rows), and the keyword
  coder's precision and recall against the agreed labels (Wilson CIs). Until every sampled comment has an
  agreed label, B4/B5 are labelled **unvalidated**. Once any label is filled in, reruns leave the sample file
  as it is.

Additions of 2026-10-27 (post hoc deviations, see change log; all descriptive, no Holm):

| ID | Measure | Method |
|---|---|---|
| B0 | Within-English halo baseline: OLS of each criterion on language_quality across English answers | bootstrap CI as B1; the cross-form slopes in B1-B2 are read against it |
| Copy check | Per judge and criterion, share of calls (all forms) with criterion = language_quality, among calls where either is below 5 | Wilson CI; at or above 90% the criterion is flagged as copying language_quality and its B0-B2 slopes are not interpreted |
| Split | B0-B3 for factual and open_ended items separately, next to the planned pooled analysis | as the pooled rows |
| Rank check | Kendall's tau-b of `dX` with `dL` next to every B0-B2 slope | tau-b and its p-value |
| Lexicon v1+zh | B4/B5 recomputed with Chinese terms added to each category (`MENTION_PATTERNS_ZH`), next to the fixed lexicon v1, plus the share of comments written in Chinese per judge and form | as B4/B5 |

## Gap A: error-detection leniency on matched wrong answers (added 2026-10-27, before any gap A call)

Each verified wrong twin (60 factual items, `wrong_qc.passed`) is scored pointwise in all four forms with the
E1 rubric and prompt (`pointwise_en`, reference-guided as in E1, so the judge sees the English reference
answer), by qwen2.5-7b-local and gpt-oss-120b: 240 calls per judge (`make run-a`, experiment `a_wrong`).
Per judge, form `f` and item `i`: `w_i(f)` = correctness of the wrong twin, `c_i(f)` = correctness of the
same item's correct answer in E1. The wrong answer's content is identical across forms, so any difference
between forms is a bias.

| ID | Measure | Method |
|---|---|---|
| A1 | False-acceptance rate: share of wrong twins with `w_i(f) >= 3` (primary) | Wilson CI per judge and form; paired vs en with an exact McNemar test (binomial on discordant items); Holm across the 3 forms per judge |
| A2 | Leniency: `w_i(f) - w_i(en)` | mean with a paired bootstrap 95% CI (10,000 resamples, seed 20261023), two-sided Wilcoxon; Holm across the 3 forms per judge |
| A3 | Discrimination margin `c_i(f) - w_i(f)`, and its change vs en | bootstrap CI, descriptive |
| A4 | Script contrast hi vs hi_rom, mixing contrast hi_rom vs hinglish, on `w` | bootstrap CI and Wilcoxon, descriptive |

- Threshold: on the rubric 1 = wrong and 5 = fully correct, so a wrong answer scored 3 or more is treated as
  at least half correct. The full score distribution per form is reported next to A1, so other thresholds can
  be read off without changing the primary one.
- With 60 items only large differences are detectable; effect sizes with CIs lead, p-values are secondary.
- Because the reference is shown, near-perfect detection in every form is a likely outcome. That result is
  reported as it is (the bias is then about scoring, not error-catching); a reference-free rerun is the
  qwen-only stretch C(ii), not part of A.
- A missing call drops its item from that comparison only; missing counts are reported per judge and form.

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
- **2026-10-26, section B added (post hoc).** Criterion leakage (B1-B3) and comment coding (B4-B5) were added
  after a literature check found them open. Timing: the Qwen E1 tables, including the descriptive
  per-criterion gaps, had already been generated (commit fc41489); the gpt-oss E1 tables and every comment had
  not been looked at. B1-B5 and the lexicon were written here before any B code was run. All of section B is
  reported as post hoc.
- **2026-10-27, section B additions after an external audit (post hoc deviations).** An audit of the shared
  section B archive raised shared-call halo, a factual-item ceiling, Chinese comments the lexicon cannot read,
  OLS on a bounded ordinal scale, and a single unblinded coder. In response: B0 (within-English baseline),
  the copy check, the factual / open_ended split, Kendall's tau-b, lexicon v1+zh, and a blind two-rater coder
  check with kappa (this replaces the single `human_mention` column; no labels had been entered). Timing: every
  B1-B5 result had been seen, and the copy check's 90% threshold was set after seeing the rates (qwen clarity
  0.91, every other judge and criterion 0.62 or lower). The Chinese terms were written after reading the
  Chinese comments. The planned B1-B5 rows (subset all, lexicon v1) are unchanged and stay the primary rows;
  every addition is descriptive.
- **2026-10-27, gap A added (before any gap A call).** A1-A4, the threshold (`w >= 3`) and the judges were
  written here, and the runner and analysis code built, before a single gap A call was made. Timing: the E1
  scores of the correct answers (used in A3) had been seen for both judges through section B; the wrong-twin
  scores had not been generated.
