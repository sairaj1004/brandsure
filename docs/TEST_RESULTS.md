# BrandSure test results (rule-based engine, AI off)

- Expected findings caught: **23 of 23**
- Cases passed: **26 of 26** (22 with expected findings, 4 clean drafts)
- False positives on clean drafts: **0**
- AI-only cases (jargon, named competitors) caught by rules alone: 0 of 2

Reproduce: `python tests/catchrate.py --write`

| Case | What it tests | Expected found | Result | Extra findings |
|---|---|---|---|---|
| R01 | wrong number: languages | 1/1 | PASS | - |
| R02 | wrong number: countries | 1/1 | PASS | - |
| R03 | wrong number: protein | 1/1 | PASS | - |
| R04 | wrong number: year | 1/1 | PASS | - |
| R05 | wrong number: delivery | 1/1 | PASS | - |
| R06 | forbidden claim | 1/1 | PASS | - |
| R07 | forbidden claim | 1/1 | PASS | - |
| R08 | needs-proof claim | 1/1 | PASS | - |
| R09 | needs-proof claim | 1/1 | PASS | - |
| R10 | glossary: product name | 1/1 | PASS | - |
| R11 | glossary: company name | 1/1 | PASS | - |
| R12 | glossary: dietary term | 1/1 | PASS | - |
| R13 | style: repeated exclamation | 1/1 | PASS | - |
| R14 | style: ALL CAPS | 1/1 | PASS | - |
| R15 | style: sentence over 25 words | 1/1 | PASS | - |
| R16 | the 3-minute demo draft (three findings) | 3/3 | PASS | - |
| R17 | superlative with no approved source | 1/1 | PASS | - |
| R18 | wrong number inside a longer text | 1/1 | PASS | - |
| I01 | low contrast | 1/1 | PASS | B2:'Text colour #CCCCC' |
| I02 | missing alt text | 1/1 | PASS | - |
| I03 | logo too small | 1/1 | PASS | - |
| I04 | clean image | 0/0 | PASS | - |
| K01 | correct number must not be flagged | 0 expected | PASS | - |
| K02 | two correct facts | 0 expected | PASS | - |
| K03 | approved term and correct fact | 0 expected | PASS | - |
| K04 | correct fact | 0 expected | PASS | - |

## Needs the AI step

| Case | What it tests | Rule-only result |
|---|---|---|
| A01 | jargon (needs AI) | not caught by rules (needs AI step) |
| A02 | named competitor (needs AI) | not caught by rules (needs AI step) |

These two are judgement calls a rule cannot make. They are the reason the optional AI check exists; its citations are re-verified in code (see `tests/test_flow.py::test_ai_citations_are_verified`).
