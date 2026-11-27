# StegnoZ — final test report

Everything below was run on this machine against the practice data on 2026-11-27.
Nothing is committed. Reproduction commands are in §7.

**Headline:** every runnable check passes. Internal re-identification exposure went
58.72% → 0.00%. The measurable cost of that change is **0.12 points of 100**.

---

## 1. The honest framing first

There is **no official score obtainable locally.** The toolkit ships three scripts —
`validate_output.py` (contract pass/fail), `check_dev.py` (a rough component guide) and
`check_submission.py` (readiness pass/fail). The official
`total = 100 × Σ weightᶜ × scoreᶜ − penalties` needs the hidden evaluator and the A1–A7
attacker, neither of which is in the kit.

So this report has two halves: **checks that are pass/fail** (authoritative), and a
**scorecard estimate** I wrote (`tools/score_estimate.py`) that recomputes the parts of
`docs/SCORING.md` derivable from `truth.json` + `scoring.toml`. The estimate covers
**57% of the official weight**. It is a self-review aid, not a result.

---

## 2. Authoritative checks — all pass

### Organizer tools

| Check | Result |
|---|---|
| `validate_output.py` | **CONTRACT OK** |
| `check_submission.py --run` | **READY TO SUBMIT** (8 repo checks, 6 runtime checks) |
| Input folder unchanged after run | **yes** |
| `RAKSHA_SECRET` in any output or log | **no** |

### `check_dev.py` — practice data

| Measure | Result |
|---|---|
| Personal data leaked | **0 of 3230 (0.0%)** |
| by script | latin 0.0%, deva 0.0%, hinglish 0.0% |
| by channel | content, filename, base64, metadata, key, header — all 0.0% |
| Canaries found | **0 of 4** (−3 each if found) |
| Medical values kept | **4855 of 4855 (100.0%)** |
| Patient linking | **P 1.00 / R 0.95 / F0.5 0.99**, 0 false merges |
| Raw copies exported | **0** (−5 each if found) |

All 16 PII categories individually at 0 leaked: PATIENT_NAME 0/962, MRN 0/850,
PHONE 0/308, RELATIVE_NAME 0/232, VILLAGE 0/150, PIN 0/136, HOUSE 0/136, DOB 0/111,
LOCALITY 0/103, AADHAAR 0/71, LANDMARK 0/64, ABHA_NUMBER 0/46, PAN 0/22,
INSURANCE_ID 0/22, AADHAAR_MASKED 0/16, EMAIL 0/1.

### Repo verification harness — `tools/verify_project.py`, 12/12 pass

```
regressions PASS   practice_run PASS   contract PASS      practice_check PASS
submission PASS    mutate PASS         mutated_run PASS   mutated_contract PASS
mutated_check PASS strict_run PASS     strict_contract PASS  strict_check PASS
input_unchanged PASS
```

`strict_run` previously **failed** here: the harness asserted that the fail-closed
default would withhold the release (exit 1). It now publishes (exit 0), so the stale
expectation was corrected and two new sub-checks added that the strict release also
passes the contract and the practice check.

### Test suite

**103 passed** (was 32 before this work). 35 new tests in `tests/test_exposure.py`
covering fact canonicalisation, coarseness rules, age-band truthfulness, ladder
ordering, the C/O traps, dose-vs-phone, eponyms, doctor retention, interval
preservation, determinism, audit hygiene, and three anti-gaming regressions.

### Determinism, keying, resources

| Check | Result |
|---|---|
| Same secret, twice → `sanitized/` byte-identical | **yes** |
| Same secret, twice → `records.jsonl` byte-identical | **yes** |
| Different secret → `sanitized/` differs | **yes** |
| Different secret → `records.jsonl` differs | **yes** |
| Runtime | **7.3–11.8 s** (limit 900 s) |
| Peak RSS | **43 MB** (limit 4096 MB) |

### `tools/attack_eval.py`

```
records 820, unresolved 38, inaccessible 0, missing_pseudonym 0
release_risk_proxy 0.0, target_met true
```

---

## 3. Generalization — unseen formats and unseen vocabulary

**Unseen formats** (`tools/mutate_dataset.py`: renamed headers, new label phrasings,
new ID shapes, alternative date formats, same PII):

| Measure | Result |
|---|---|
| Leak | **0 of 3230 (0.0%)** |
| Medical | 4855/4855 (100.0%) |
| Linking | P 1.00 / R 0.96 / F0.5 0.99 |
| Contract | CONTRACT OK |

**Unseen vocabulary** (`tools/synth_dataset.py`, new: names, places and IDs built from
syllable and digit patterns, nothing copied from `dev/truth`). Covers Devanagari and
Hinglish, surname-first, initials, honorifics, Mohammad/Mohd./Md. variants,
S/o–D/o–W/o and पुत्र/पुत्री, +91 / 0-prefix / bracketed / Devanagari-digit phones,
Verhoeff-valid Aadhaar, 14-digit ABHA, PAN, UHID, insurance IDs, PII in JSON keys,
FHIR `name`/`telecom`/`address`/`text.div`, base64 attachments, PII in a file name,
cp1252 and utf-16 files, and a truncated JSON.

| Seed | PII leaked | Clinical kept |
|---|---|---|
| 20261127 | **0 / 630** | 108 / 108 |
| 7 | **0 / 630** | 110 / 110 |
| 99 | **0 / 630** | 109 / 109 |
| 31337 | **0 / 630** | 108 / 108 |

---

## 4. Scorecard estimate — before vs after

`tools/score_estimate.py`, covering 57% of the official weight. **Not the official
score.** "Before" is the pre-change release in `_eval/base`.

| Category | Weight | Before | After | Δ |
|---|---:|---:|---:|---:|
| 1 Detection (F2) | 20% | 1.000 | **1.000** | — |
| &nbsp;&nbsp;recall | | 1.000 | 1.000 | — |
| &nbsp;&nbsp;contextual precision | | 1.000 | 1.000 | — |
| 2 Identity (0.70 of category scorable) | 15% | 0.691 | **0.691** | — |
| &nbsp;&nbsp;F0.5 / B³F1 | | 0.990 / 0.981 | 0.990 / 0.981 | — |
| 3 Privacy | 25% | *not computable* | *not computable* | — |
| 4 Utility (85% of category covered) | 20% | 0.943 | **0.936** | −0.007 |
| &nbsp;&nbsp;clinical probes | | 100.0% | 100.0% | — |
| &nbsp;&nbsp;temporal (intervals) | | 98.1% | 98.1% | — |
| &nbsp;&nbsp;token retention | | 94.4% | 93.9% | −0.5pp |
| &nbsp;&nbsp;record retention | | 97.0% | 97.0% | — |
| &nbsp;&nbsp;age generalization | | 0.637 | 0.582 | −0.055 |
| 5 Integrity | 10% | *see validate_output* | *CONTRACT OK* | — |
| 6 Performance | 10% | 1.000 | **1.000** | — |
| Penalties | | 0 | **0** | — |
| **Computed points** | **57%** | **56.39** | **56.27** | **−0.12** |

All ten Challenge-2 contextual-precision trap groups score **100%**: `doctor`,
`doctor-vs-relative`, `c/o-complaint`, `k/c/o`, `h/o`, `hospital-ward`, `dose`,
`1-0-1`, `eponym`, `asha`. Clean-document token retention 100%.

**Reading this honestly:** the measurable cost of taking exposure from 58.72% to 0.00%
is **0.12 points of 100**, all of it in two utility sub-parts (age bands widened from
5 to 10 years; village/tehsil generalised to district, which also costs 0.5pp of token
retention). The benefit lands in the privacy category — 25% of the total, the single
heaviest — which cannot be measured here. A3 and A4 depend directly on geography and
age granularity, which is exactly what was coarsened.

---

## 5. Internal exposure — before vs after

| Measure | Before | After |
|---|---:|---:|
| `singling_out_risk` | 58.72% | **0.00%** |
| same with `population_factor: 1` (assumption off) | 58.72% | **0.00%** |
| `rare_dx_exposed_profiles` | 18 | **0** |
| `target_met` | false | **true** |
| strict / fail-closed run | withheld all, exit 1 | **publishes, exit 0** |
| patients locally recoded | n/a | **0** |
| selected node | (5y, tehsil, PIN prefix) | (10y, district, PIN prefix) |
| `release_profile_uniqueness` (reported, not targeted) | 0.5872 | 0.5872 |

`raksha.toml` no longer passes `--allow-risk-miss`: the submission publishes under the
strict policy rather than through the escape hatch.

---

## 6. Known limitations

1. **Privacy (25%) and Integrity (10%) are not measured here.** No attacker ships with
   the kit. Integrity is largely covered by `validate_output.py` returning CONTRACT OK.
2. **The 0.00% rests on one definitional rule.** All 50 quasi-identifier-bearing
   profiles are excluded by `narrows_population` — the judgement that district + sex +
   a ≥10-year band is tens of thousands of people — rather than by cell arithmetic.
   `k_target` is consequently inert on this data (2, 5, 10, 20, 50 all give 0.00%).
   This is the assumption most worth stating plainly in the brief.
3. **`population_factor: 4` is declared, not measured.** After the anti-gaming fix it
   cannot change the released bytes at all — only the verdict — and the result is
   0.00% at every factor from 1 to 5. `observed_singling_out_risk` is always published.
4. **`release_profile_uniqueness` stays 0.5872.** Per-patient shifted event weeks and
   preserved diagnoses make most records distinct as records. Both are required by the
   challenge and neither is reachable by generalising quasi-identifiers.
5. **Rare diagnoses.** For a condition only one patient has, the diagnosis identifies
   the record whatever is done to quasi-identifiers; suppressing or generalising the
   code is forbidden. 0 exposed here, but that is a property of this dataset.
6. **The scorecard estimate has approximations.** Age generalization grades only
   published age fields (283 of 552 age fields are in exports that never carried an
   age — `lab/bulk_lab_export.json` has no age key in the baseline either, so this is
   pre-existing, not a regression). Identity traps (0.045 of total) and utility
   statistics (0.03 of total) are not graded.
7. **Fail-closed withholding is now a backstop, not routine**, because local recoding
   terminates in suppression. It still fires for a profile the recoder cannot reach and
   is covered by a direct test.

---

## 7. Reproducing every number

```powershell
cd C:\Users\ASUS\Desktop\stegnoZ\RakshaMed
```

Run the pipeline (fail-closed default, no escape hatch):

```powershell
$env:RAKSHA_SECRET="practice"; python main.py --input ..\toolkit2\dev\input --output _eval\final
```

Organizer checks:

```powershell
python ..\toolkit2\validate_output.py --input ..\toolkit2\dev\input --output _eval\final
```

```powershell
python ..\toolkit2\check_dev.py --output _eval\final
```

```powershell
$env:PYTHONUTF8="1"; python ..\toolkit2\check_submission.py --repo . --run
```

Full verification harness (12 checks):

```powershell
$env:PYTHONUTF8="1"; python tools\verify_project.py --toolkit ..\toolkit2 --output _verify
```

Test suite:

```powershell
python -m pytest tests -q
```

Scorecard estimate:

```powershell
python tools\score_estimate.py --release _eval\final --toolkit ..\toolkit2
```

Unseen-vocabulary generalization:

```powershell
python tools\synth_dataset.py --out _eval\synth --seed 7 --patients 35; $env:RAKSHA_SECRET="practice"; python main.py --input _eval\synth --output _eval\synthout; python tools\synth_dataset.py --out _eval\synth --score _eval\synthout
```

Unseen-format generalization:

```powershell
python tools\mutate_dataset.py ..\toolkit2\dev\input _eval\mut --truth ..\toolkit2\dev\truth\truth.json --truth-output _eval\mut-truth.json
```

Local risk inspector:

```powershell
python tools\attack_eval.py --output _eval\final
```
