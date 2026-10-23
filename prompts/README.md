# Prompts

All prompt text lives here, in plain UTF-8. Placeholders are `{name}` and are filled by exact string
replacement (not `str.format`), so the literal JSON braces in the prompts are safe.

| File | Version | Status |
|---|---|---|
| pointwise_en.txt | v1 | Text from brief section 5.1 |
| pairwise_en.txt | v1 | Text from brief section 5.2 |
| pointwise_hi.txt | v1-draft | **Drafted by Claude (claude-opus-5-5). Needs a Hindi speaker to verify before E5.** |
| pairwise_hi.txt | v1-draft | **Drafted by Claude (claude-opus-5-5). Needs a Hindi speaker to verify before E5.** |
| bias_aware_suffix.txt | v1 | Text from brief section 5.3(c) |
| translate_to_en.txt | v1 | Fixed translator prompt for E5(b) |

The JSON keys in the Hindi prompts stay in English so the same parser works for every variant.

The `{reference_block}` placeholder becomes `Reference answer: <reference_en>` (English prompts) or
`संदर्भ उत्तर: <reference_en>` (Hindi prompts) for reference-guided items, and an empty line otherwise.

Any edit to a prompt changes its cache key, so it produces new calls. Bump the version in this table when
you change a prompt.
