# Results so far (draft, 2026-10-27)

Working summary of the main-study results, for the team and the report. **Draft: not reviewed by the team.**
Every number is copied from a generated table in `results/tables/` (named in each section), which `make
reproduce` plus the stats targets rebuild offline from the logged responses (checked 2026-10-27: identical).
Comparisons and tests are the ones fixed in `analysis/plan.md`; anything post hoc is marked.

**Scope.** 150 verified quadruples (100 factual, 50 open-ended), 60 verified wrong twins. Two judges:
gpt-oss-120b (Groq) and qwen2.5-7b-local (Ollama). gemini-flash is in the plan but has pilot calls only, so
none of the results below include it. E4 (human grading) has not started, so no result here says whether the
judges agree with Hindi speakers. Gaps are form minus English on the same item, on the 1-5 scale; "content" is
the mean of correctness, completeness and clarity.

## Headline

1. **Script, not language.** Both judges score the same Hindi answer lower in Latin script than in
   Devanagari (content +0.19 and +0.18 for Devanagari, both p < 0.001), and both penalise Romanized Hindi
   and Hinglish more than Devanagari Hindi.
2. **gpt-oss-120b** gives Devanagari Hindi the same content score as English (+0.02, n.s.) but marks Romanized
   Hindi and Hinglish down by 0.16 (both p < 0.001), mostly through clarity. Pairwise, it never prefers the
   Hindi-form answer: English wins every non-tie judgment in all three pairs. It never picks a wrong English
   answer over a correct one (0/60 in every E3 cell).
3. **qwen2.5-7b-local** is noisier and position-biased, and its pooled gaps hide two opposite effects: it
   scores non-English answers *higher* on factual items (+0.17 to +0.32) and *lower* on open-ended ones
   (-0.17 to -0.65). It lets wrong answers through far more often in Romanized forms (gap A: 58% of wrong
   Romanized-Hindi answers accepted vs 17% in English).
4. **Mitigations (first results).** Adding a "do not judge the language" instruction does nothing measurable
   for Qwen. A two-judge majority vote helps Qwen and hurts gpt-oss-120b; with two judges it is not a real
   majority (every disagreement becomes a tie).

## E1: pointwise gap (`main_baseline.md`)

Content gap, form minus English, n = 150, bootstrap 95% CI, Holm-adjusted Wilcoxon p.

| Comparison | gpt-oss-120b | qwen2.5-7b-local |
|---|---|---|
| E1.1 hi vs en | 0.02 [-0.02, 0.08], p = 1.000 | **0.16 [0.06, 0.25], p = 0.006** |
| E1.2 hi_rom vs en | **-0.16 [-0.21, -0.12], p < 0.001** | -0.02 [-0.14, 0.09], p = 0.960 |
| E1.3 hinglish vs en | **-0.16 [-0.22, -0.11], p < 0.001** | -0.10 [-0.21, 0.01], p = 0.268 |
| E1.4 hi vs hi_rom | **0.19 [0.14, 0.24], p < 0.001** | **0.18 [0.09, 0.27], p = 0.002** |
| E1.5 hi_rom vs hinglish | 0.00 [-0.05, 0.06], p = 1.000 | 0.08 [-0.00, 0.16], p = 0.187 |

- **gpt-oss-120b, by criterion:** the Romanized-form drop is clarity (-0.55 hi_rom, -0.42 hinglish) and
  language quality (-0.61, -0.47); correctness and completeness barely move (-0.08 to +0.11). At equal answer
  length the hi_rom and hinglish gaps shrink to -0.09 and -0.08, so part of the gap goes with length.
- **qwen2.5-7b-local, by item type (exploratory):** factual items run positive (hi +0.32, hi_rom +0.26,
  hinglish +0.17, all p ≤ 0.002), open-ended items negative (hi -0.17, hi_rom -0.59, hinglish -0.65). The
  pooled near-zero hi_rom and hinglish gaps average these out. Its overall score (all four criteria) does drop
  for Hinglish (-0.15, p = 0.010).
- gpt-oss-120b by type: the Hinglish gap is much larger on open-ended items (-0.38) than factual (-0.06).

## E2: pairwise preference (`main_baseline.md`)

Each order counts as one judgment. English win-rate is among non-tie judgments.

| Pair | gpt-oss-120b: English wins | ties | qwen2.5-7b-local: English wins | ties | Qwen A-slot rate |
|---|---|---|---|---|---|
| en vs hi | 139/139 (1.00) | 54% | 174/300 (0.58) | 0% | 0.81 |
| en vs hi_rom | 224/224 (1.00) | 25% | 226/300 (0.75) | 0% | 0.72 |
| en vs hinglish | 200/200 (1.00) | 33% | 206/298 (0.69) | 0% | 0.80 |

- gpt-oss-120b often calls it a tie, but when it picks, it picks English, even for Devanagari Hindi, where
  its pointwise scores show no gap. Pairwise framing exposes a preference the pointwise scores do not.
- Qwen never ties and prefers whichever answer is shown first 72-81% of the time; it gives the same verdict
  in both orders on only 33-52% of items. Where it is order-consistent, English wins 74% (hi), 99% (hi_rom)
  and 98% (hinglish).

## E3: wrong English vs correct non-English answer (`main_baseline.md`)

"Consistent" = the wrong English answer wins in both orders. Control = correct English vs wrong English.

| Correct form | gpt-oss-120b consistent | qwen2.5-7b-local consistent | Qwen any-order |
|---|---|---|---|
| hi | 0/60 | 5/53 (0.09 [0.04, 0.20]) | 40/53 (0.75) |
| hi_rom | 0/60 | 7/54 (0.13 [0.06, 0.24]) | 35/54 (0.65) |
| hinglish | 0/60 | 6/55 (0.11 [0.05, 0.22]) | 33/55 (0.60) |
| en (control) | 0/60 | 0/59 | 8/59 (0.14) |

- Qwen's high any-order rates are mostly its position bias (it picks slot A); the consistent rate is the one to
  quote. That is 9-13% against 0% in the control, so a correct answer in a Hindi form loses to a wrong English
  answer on about one item in ten. Qwen has 5-7 cells per form missing (unparsed after retries).

## Gap A: wrong answers scored pointwise (`main_baseline_a.md`, qwen2.5-7b-local only)

Pre-registered in `analysis/plan.md` before any call. False acceptance = wrong twin's correctness ≥ 3.
McNemar vs the same item's wrong English answer, Holm across forms.

| Form | Accepted | vs en | Leniency (mean score change vs en) | Margin (correct minus wrong) |
|---|---|---|---|---|
| en | 10/60 (0.17 [0.09, 0.28]) | - | - | 2.67 |
| hi | 17/60 (0.28 [0.19, 0.41]) | +0.12, p = 0.039 | +0.33 [0.13, 0.55] | 2.70 |
| hi_rom | 35/60 (0.58 [0.46, 0.70]) | +0.42, p < 0.001 | +0.97 [0.73, 1.20] | 1.98 |
| hinglish | 27/60 (0.45 [0.33, 0.58]) | +0.28, p < 0.001 | +0.62 [0.42, 0.83] | 2.22 |

- Qwen separates right from wrong as well in Devanagari as in English (margin change +0.03, n.s.), but
  less well in Romanized Hindi (-0.68 [-0.95, -0.42]) and Hinglish (-0.45 [-0.70, -0.20]). Devanagari vs
  Romanized is again the large contrast (-0.63, p < 0.001).
- Not yet run for gpt-oss-120b (240 Groq calls).

## Section B: criterion leakage and comments (`main_baseline_b.md`, post hoc, exploratory)

All criteria come from one judge call, so co-movement is not evidence of cause.

- **Qwen moves all criteria together even in English.** Within English answers, a one-point change in
  language quality goes with 0.93 points of correctness and 1.14 of completeness (Kendall tau 0.50). Its
  cross-form slopes (0.74-0.84) are no larger, so for Qwen the data cannot separate language leaking into
  content from a general halo. Its clarity score repeats language quality in 91% of off-ceiling calls (flagged
  as a copy; its clarity slopes say nothing about leakage).
- **gpt-oss-120b keeps the criteria apart in English** (within-English slopes near zero or negative). On
  factual items its correctness is 5 for every form, so nothing can leak there. On open-ended items,
  correctness drops with language quality for Romanized Hindi (slope 0.43 [0.19, 0.63]) and Hinglish
  (0.46 [0.22, 0.69]), which fits language quality leaking into the content score on open-ended answers.
  Its clarity follows language quality (B2 slope 0.79 for hi_rom).
- **Comments (keyword coder, not yet checked by humans: 0 of 200 sample comments labelled).** gpt-oss-120b
  names language in 87% / 75% / 53% of its hi / hi_rom / hinglish comments (2% for English); Qwen in 16% /
  33% / 16%. With the post-hoc Chinese lexicon Qwen's hi rate is 29%, because Qwen wrote many of its comments
  on Hindi answers in Chinese. Of Qwen's content drops vs English, 65-87% come with a comment that never
  mentions language ("silent penalties"); for gpt-oss-120b it is 10-31%.

## E5: mitigations (`main_e5.md`, 60-item subset)

Each variant is compared with the same judge's baseline on the same 60 items (40 factual with wrong twins,
20 open-ended); change = variant minus baseline with a bootstrap 95% CI.

**Bias-aware prompt (qwen2.5-7b-local, 920 calls, run 2026-10-27).** The baseline prompt plus a short instruction
(`prompts/bias_aware_suffix.txt`) that the language or script must not affect the scores. It changes almost nothing:

| Measure | hi | hi_rom | hinglish |
|---|---|---|---|
| Absolute content gap vs en | 0.42 → 0.43 (+0.01 [-0.09, 0.10]) | 0.52 → 0.53 (+0.01 [-0.07, 0.09]) | 0.53 → 0.47 (-0.07 [-0.15, 0.01]) |
| E2 English win-rate | 0.57 → 0.63 (+0.07 [0.02, 0.12]) | 0.76 → 0.80 (+0.04 [0.01, 0.08]) | 0.73 → 0.72 (-0.01 [-0.04, 0.03]) |
| Consistent wrong-English rate | 0.12 → 0.09 (-0.03 [-0.09, 0.00]) | 0.14 → 0.14 | 0.14 → 0.14 |

- Control accuracy 0.86 → 0.81 (-0.05 [-0.14, 0.00]): no clear accuracy cost, and no clear gain anywhere.
  The only CIs that exclude zero are the E2 rows for hi and hi_rom, and they move the wrong way (English
  preferred slightly more). Telling a 7B judge to ignore language does not stop it from using language.
- 26 of 920 calls stayed unparsed after retries (1 in E2, 25 in E3), similar to Qwen's baseline E3; E3
  cells need both orders, so n is 33-37 instead of 40.

**Majority vote** (needs no new calls). It combines the two judges' existing baseline verdicts and is compared
with each judge's own baseline.

| | vs qwen2.5-7b-local | vs gpt-oss-120b |
|---|---|---|
| Absolute content gap vs en | narrower by 0.16-0.23 | wider by 0.08-0.17 |
| Consistent wrong-English rate | 0.11-0.14 → 0.00 | 0.00 → 0.00 |
| Control accuracy | 0.87 → 0.87 | 1.00 → 0.87 (-0.13 [-0.26, -0.03]) |
| E2 English win-rate | 0.57-0.76 → 1.00 | 1.00 → 1.00 |

- The E2 row is mechanical: with two judges, a non-tie majority needs both to agree, and gpt-oss-120b's
  non-tie picks are always English. A third judge is needed before majority vote can be judged fairly.
- Not started: bias-aware on gpt-oss-120b, translate-then-judge (Groq translator) and the Hindi rubric
  (needs a Hindi speaker to check the prompts).

## Not done yet

- gemini-flash main study (pilot only); gpt-oss-120b gap A; E5 bias-aware for gpt-oss-120b; E5
  translate-then-judge; E5 Hindi rubric; E4 human grading; the two-rater check of the comment coder.
- Two judges is a small panel. Every Hindi-form text was machine-drafted and then human-verified; see the
  README limitations.
