# StegnoZ — an offline multilingual healthcare privacy firewall

StegnoZ is a privacy firewall for the **Secret Wards** challenge (Track 3). It ingests a chaotic
dump of Indian hospital records — CSV, TSV, nested JSON, FHIR R4 bundles and free-text notes, in
English, Devanagari Hindi and Hinglish, across four hospital systems and several encodings — and
produces a research-safe release that removes every direct identifier and quasi-identifier while
keeping every medically useful value intact, gives each real patient one stable pseudonym across
all files and languages, and leaks nothing to any side channel. It runs **fully offline, on CPU,
with no large language model, no generative model and no pretrained transformer of any size** — the
entire detection, linkage and privacy stack is implemented from scratch in this repository using
only the Python standard library.

## Why it is hard, and how StegnoZ answers each trap

The same patient appears as `Mohammad Arif`, `मोहम्मद आरिफ`, `Md. Arif` and `Arif sahab ka BP 150/90`,
each with a different phone format, a half-written address and a different hospital ID. Names hide in
JSON keys, CSV headers, file names, FHIR narratives and base64 attachments. Numbers that look like
identifiers are really doses (`1-0-1`, `Dolo 650 BD x 5 days`). After submission an automated
attacker holding a voter roll and a few known facts (a visit date, a rare disease, a length of stay)
tries to re-identify every patient. StegnoZ is built around these traps rather than around the
practice files, so it survives the hidden datasets that use column names, labels and formats never
seen in practice.

## Architecture

A five-pass pipeline (see `raksha/`):

1. **Ingestion** (`ingest.py`) — content-sniffed format detection (JSON behind a `.csv` extension is
   still JSON; FHIR is detected by `resourceType`), robust decoding (UTF-8/BOM, UTF-16, cp1252),
   Devanagari-digit and zero-width normalisation, and guards for deeply nested, truncated, corrupt,
   binary or empty files, each **quarantined** with a PII-free reason rather than copied out raw.
2. **Schema intelligence + extraction** (`extract.py`, `lexicon.py`) — every column header and JSON
   key is classified into a field kind using a multilingual lexicon, fuzzy matching (misspelled
   keys), JSON-parent and FHIR-resource context, **and content voting** over the column's values, so
   an unseen header such as `EnrolmentRef` or `cell_contact` is still recognised from what it holds.
   Unknown columns are scanned as free text, never passed through. A **run-only dynamic dictionary**
   of every name and identifier seen anywhere is built here.
3. **Identity resolution** (`link.py`, `translit.py`) — records are blocked by strong identifiers
   and by a custom **Indic phonetic key** (cross-script, order-free), compared on discrete agreement
   levels, and scored with **Fellegi–Sunter weights whose m/u probabilities are estimated per run by
   EM** (no labels, deterministic), so the model adapts to unseen data instead of being hand-tuned.
   **Constrained merge-center clustering** with cannot-link rules (different DOB, gender, relative or
   incompatible age) keeps same-name patients apart and prevents transitive over-merging. Uncertain
   links are left unresolved. Pseudonyms are keyed **HMAC-SHA256** (HKDF-separated keys), so they are
   non-reversible and change with the secret.
4. **Privacy layer** (`privacy.py`) — per-patient secret **date shifting** (never small, never
   shared) keeps every interval and length-of-stay exact while defeating global-offset recovery. The
   **Reverse Privacy Engine** builds a Patient Exposure Graph (each patient's pooled quasi-identifiers
   and hospital/diagnosis trail), then searches the generalisation lattice (age band 5/10/20 ×
   location tehsil/district × PIN prefix/drop) for the **least destructive node meeting the risk
   target**, and applies **Mondrian-style local recoding** that coarsens only the patients still in
   small or rare-diagnosis classes. Age bands always contain the true age.
5. **Rewriting + self-correcting verification** (`sanitize.py`, `pipeline.py`) — format-preserving
   rewriters for CSV, JSON, FHIR (references stay resolvable, narratives and base64 attachments are
   scrubbed) and text. Hidden channels (base64, hex, `\u`, HTML entities, %-encoding, homoglyphs) are
   decoded before detection and re-encoded after. A final **residual scan** re-reads every output,
   re-redacts anything missed, and quarantines any file it cannot make safe.

## Security design

`RAKSHA_SECRET` is read once, expanded with HKDF into purpose-separated keys (pseudonyms, date
shifts, file-name tags) and never printed, logged or written. Logs carry only counters and exception
*types*. No temporary files are created; nothing touches the network. The same input and secret give
byte-identical output; a different secret gives different pseudonyms and date shifts.

## Run it

```bash
RAKSHA_SECRET=<secret> python main.py --input <input_dir> --output <output_dir>
```

Outputs `sanitized/`, `report.json`, `records.jsonl` (and a development `audit.json`). Privacy
targets live in `config/policy.yaml`. Development tools (`tools/attack_eval.py`, `tools/mutate_dataset.py`)
are for local tuning only and never run in the submission.

## Models declaration

**None.** No LLM, no generative model, no pretrained transformer. All detection, transliteration, EM
record linkage, k-anonymity lattice search and Mondrian recoding are original code in this repo.

## Known limitations

The re-identification risk reported in `audit.json` is a measured proxy, not a guarantee; a
determined attacker with richer side knowledge than modelled may still single out a patient with a
genuinely unique clinical signature. Free-text detection is high-recall by design and may over-redact
a rare name that collides with a medical term. Transliteration covers common Hindi/Hinglish name
morphology but not every regional spelling.
