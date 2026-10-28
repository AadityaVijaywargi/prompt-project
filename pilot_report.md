# Pilot Report: Language-Bias Auditor for LLM Judges (Phase 0)

> [!IMPORTANT]
> **PILOT and exploratory (n = 20, below 30).**
> Prompt variant: `baseline`.
> All metrics are generated strictly from the pilot results files under `results/tables/`.
> Pilot items are preliminary and are not pooled with later main results.

## 1. E1: Pointwise Rubric Grading

Signed gap vs English (or reference form): `score(form) - score(en)` on 1-5 scale.
Primary measure is **content score** (mean of correctness, completeness, clarity); overall is secondary.

| Judge | Comparison | Measure | n | Mean Gap | 95% CI | Wilcoxon p | Holm p | Verbosity Intercept | Verbosity Slope |
|---|---|---|---|---|---|---|---|---|---|
| gemini-flash | hi vs en | content | 20 | +0.000 | [0.000, 0.000] | 1.0000 | 1.0000 | 0.000 | 0.000 |
| gemini-flash | hi_rom vs en | content | 20 | +0.000 | [0.000, 0.000] | 1.0000 | 1.0000 | 0.000 | 0.000 |
| gemini-flash | hinglish vs en | content | 20 | +0.000 | [0.000, 0.000] | 1.0000 | 1.0000 | 0.000 | 0.000 |
| gemini-flash | hi vs hi_rom (script) | content | 20 | +0.000 | [0.000, 0.000] | 1.0000 | 1.0000 | N/A | N/A |
| gemini-flash | hi_rom vs hinglish (mixing) | content | 20 | +0.000 | [0.000, 0.000] | 1.0000 | 1.0000 | 0.000 | 0.000 |
| gemini-flash | hi vs en (overall) | overall | 20 | +0.000 | [0.000, 0.000] | 1.0000 | N/A | 0.000 | 0.000 |
| gemini-flash | hi_rom vs en (overall) | overall | 20 | +0.000 | [0.000, 0.000] | 1.0000 | N/A | 0.000 | 0.000 |
| gemini-flash | hinglish vs en (overall) | overall | 20 | +0.000 | [0.000, 0.000] | 1.0000 | N/A | 0.000 | 0.000 |
| gpt-oss-120b | hi vs en | content | 20 | -0.050 | [-0.100, 0.000] | 0.0833 | 0.2498 | 0.023 | -0.563 |
| gpt-oss-120b | hi_rom vs en | content | 20 | -0.183 | [-0.333, -0.050] | 0.0422 | 0.1687 | 0.015 | -1.520 |
| gpt-oss-120b | hinglish vs en | content | 20 | -0.167 | [-0.300, -0.067] | 0.0169 | 0.0847 | -0.125 | -0.470 |
| gpt-oss-120b | hi vs hi_rom (script) | content | 20 | +0.133 | [0.017, 0.267] | 0.1148 | 0.2498 | N/A | N/A |
| gpt-oss-120b | hi_rom vs hinglish (mixing) | content | 20 | -0.017 | [-0.167, 0.117] | 0.9434 | 0.9434 | -0.034 | 0.416 |
| gpt-oss-120b | hi vs en (overall) | overall | 20 | -0.050 | [-0.100, -0.013] | 0.0455 | N/A | 0.002 | -0.401 |
| gpt-oss-120b | hi_rom vs en (overall) | overall | 20 | -0.263 | [-0.450, -0.100] | 0.0066 | N/A | -0.043 | -1.684 |
| gpt-oss-120b | hinglish vs en (overall) | overall | 20 | -0.237 | [-0.400, -0.100] | 0.0070 | N/A | -0.180 | -0.643 |

## 2. E2: Pairwise Preference (Both Orders)

Evaluates whether judges systematically prefer English over semantically identical Hindi/Romanized/Hinglish answers.

| Judge | Pair | n Items | En Wins | Form Wins | Ties | En Win Rate (95% CI) | Binom p | Holm p | Tie Rate (95% CI) | Position Consistency (95% CI) | A-Slot Rate (95% CI) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini-flash | en vs hi | 20 | 39 | 0 | 1 | 1.000 [0.910, 1.000] | 0.0000 | 0.0000 | 0.025 [0.004, 0.129] | 0.950 [0.764, 0.991] | 0.513 [0.362, 0.661] |
| gemini-flash | en vs hi_rom | 20 | 40 | 0 | 0 | 1.000 [0.912, 1.000] | 0.0000 | 0.0000 | 0.000 [0.000, 0.088] | 1.000 [0.839, 1.000] | 0.500 [0.352, 0.648] |
| gemini-flash | en vs hinglish | 20 | 40 | 0 | 0 | 1.000 [0.912, 1.000] | 0.0000 | 0.0000 | 0.000 [0.000, 0.088] | 1.000 [0.839, 1.000] | 0.500 [0.352, 0.648] |
| gpt-oss-120b | en vs hi | 20 | 16 | 0 | 24 | 1.000 [0.806, 1.000] | 0.0000 | 0.0000 | 0.600 [0.446, 0.737] | 0.700 [0.481, 0.855] | 0.500 [0.280, 0.720] |
| gpt-oss-120b | en vs hi_rom | 20 | 27 | 0 | 13 | 1.000 [0.875, 1.000] | 0.0000 | 0.0000 | 0.325 [0.201, 0.480] | 0.750 [0.531, 0.888] | 0.556 [0.373, 0.724] |
| gpt-oss-120b | en vs hinglish | 20 | 30 | 0 | 10 | 1.000 [0.886, 1.000] | 0.0000 | 0.0000 | 0.250 [0.142, 0.402] | 0.700 [0.481, 0.855] | 0.567 [0.392, 0.726] |

## 3. Notes & Limitations

- All pilot numbers are strictly sourced from `results/tables/pilot_e1_pointwise.csv` and `results/tables/pilot_e2_pairwise.csv`.
- Due to small sample size (n=20), confidence intervals are wide and p-values are exploratory.
- Main findings will be established in Phase 2 with full dataset (N=150) and complete judge panel.
