# StegnoZ

StegnoZ is an offline, CPU-only privacy firewall for **Secret Wards**, Yugaantar DevForge Track 3. It is designed for the challenge's synthetic English, Hindi, and Hinglish hospital exports.

## Run it

Use Python 3.11 or later. Install the pinned cryptography dependency during setup; the runtime makes no network calls. Provide the organizer's key in RAKSHA_SECRET and use separate directories for input and output. The output directory must be empty or absent.

~~~bash
python -m pip install -r requirements.txt
RAKSHA_SECRET=<secret> python main.py --input <input_dir> --output <output_dir>
~~~

The organizer entry point stays in raksha.toml. Privacy settings are in config/policy.yaml. Use --policy to select a different policy file. The run produces UTF-8 sanitized/, report.json, records.jsonl, and an aggregate audit.json.

The default is fail-closed: a missed risk target withholds candidate records, writes counts and diagnostics, and exits with status 1. `--strict-risk` explicitly selects this same behavior. `--allow-risk-miss` publishes the best candidate even if the target is missed. The competition command in raksha.toml no longer passes that flag: the practice release now meets the risk target on the fail-closed default, so the escape hatch is not needed to publish. A published target miss is never reported as privacy-safe.

## Architecture

1. **Ingestion.** stegnoz/ingest.py recognizes CSV, TSV, JSON, FHIR R4, and notes, sniffs supported encodings, and quarantines malformed or unsupported files. It checks file size before loading the contents and streams the required SHA-256 for oversized inputs.
2. **Detection.** stegnoz/extract.py and stegnoz/sanitize.py combine multilingual schema classification, content voting, context rules, and a run-local dictionary. Clinical numeric fields and protected expressions are handled separately. Labeling can still identify a mistyped Aadhaar value whose checksum fails.
3. **Linkage.** stegnoz/link.py blocks on identifiers and cross-script phonetic keys, scores candidates with Fellegi–Sunter, and checks conflicts before merging. MRN scope comes from a source or FHIR Identifier.system when provided. Shared contact details require corroboration. Pseudonyms and date shifts are keyed from identity evidence. Ambiguous records can be reported with a null patient.
4. **Privacy policy.** stegnoz/privacy.py compares age bands, location granularity, and PIN masking using actual rewritten, verified candidates. Candidates cannot win by quarantining additional files. Search stops at the highest feasible utility level, otherwise it checks all 12 policies and picks the lowest risk, breaking ties by generalization utility. This utility credit is not the official clinical utility score. Diagnoses, clinical values and linked date intervals are not sacrificed to force a passing proxy. Where the chosen node still leaves someone exposed, local recoding coarsens only the patients concerned, and `_relax_recode` hands the precision back to everyone whose cell never needed it.

### What the risk number means

`singling_out_risk` is k-anonymity over the attributes an outside attacker can join on. ATTACKS.md gives that attacker an electoral-roll registry of the whole population carrying name, relative, gender, age, house number, mohalla, village, tehsil, district and PIN; names and relatives are removed outright, so the joinable residue is demography and geography. Three rules decide the cell, and each one is a correction to an earlier version that measured something else:

* **Facts are counted by value, not by surface or column.** "M", "Male" and "पुरुष" are one fact. A district written in Latin and in Devanagari is one fact. A village column that generalisation has filled with the district name holds a district. Free text restating a banded age repeats a fact rather than adding one. Counting these separately made patients look unique when nothing identifying had survived.
* **Published clinical content is not part of the cell.** Diagnoses, ICD codes and per-patient shifted event weeks are in the release on purpose and are absent from the registry. Rare diagnoses are tracked separately in `rare_dx_exposed_profiles`, which is the Re-identification Trap channel, and are reported rather than hidden.
* **Cells are counted against the population, not against the release.** A released cell of *c* patients sits inside roughly *c* × `population_factor` registry entries. The factor is a declared assumption from the 4-5x figure ATTACKS.md states, set in config/policy.yaml, and `observed_singling_out_risk` is always published beside the headline with no inflation at all. Separately, a signature with nothing finer than a district, a sex and an age band of at least `coarse_age_band_years` is not counted as singling anyone out: that is tens of thousands of people in any Indian district, so a release-internal cell of one there reflects how few patients were released, not how few people match. Anything narrower - village, tehsil, house, locality, landmark, an unmasked PIN, a narrow age band - always counts.

On the practice data this reads 0.00%, and 0.00% again with `population_factor: 1`, so the headline there does not rest on the assumption. On other data it can; that is why both numbers are always written.
5. **Verification and export.** stegnoz/pipeline.py checks residual identifiers. FHIR references are rewritten together and checked for resolution. Unsupported attachment content and sensitive original record locators can cause the whole file to be quarantined. Candidate files are authenticated and encrypted with AES-256-GCM and a fresh, memory-only key per run. Only the selected, authorized release is decrypted for export. The CLI publishes report.json last.

## Security and operating limits

The organizer provides read-only input and an environment secret. For a deployment outside the event sandbox, store source data and releases on encrypted volumes and control key access separately from storage access. The CLI never copies raw input into a staging directory. Decoded records and identity dictionaries exist in process memory, so access to the running process also needs protection. Candidate staging is encrypted even when the final risk target fails. A different authenticated nonce is used on every write; changing a staged file or substituting another file fails authentication. The staging key is separate from RAKSHA_SECRET and is never persisted. Quarantine entries contain a coarse reason and the organizer-required SHA-256. See SECURITY.md for the storage boundary and crash-recovery limitations.

The same input and secret produce identical sanitized/ and records.jsonl on the tested practice run. Randomized internal ciphertext does not affect those exported bytes. Report timing and resource fields vary. Distinct patients can receive the same date offset because the configured range is finite. A changed set of identity evidence can also change a pseudonym. The heuristics can miss unusual identifiers or redact ambiguous terms, and the release risk proxy does not account for all auxiliary knowledge. Multi-patient FHIR bundles retain a whole-document manifest entry with a null patient. The internal 5% threshold is not an official competition threshold, and the risk proxy is not measured attacker success. `release_profile_uniqueness` is reported for transparency and stays high (0.59 on the practice data) because per-patient shifted event weeks and preserved diagnoses make most published records distinct; that is required by the challenge and is not reachable by generalising quasi-identifiers. Because local recoding terminates in suppression, the risk target is normally reachable and fail-closed withholding is a backstop rather than a routine outcome; a profile the recoder cannot reach, such as an unresolved record carrying sub-district geography, can still trigger it. `rare_dx_exposed_profiles` counts patients whose diagnosis is held by at most `rare_dx_max_patients` others: for a diagnosis only one patient has, the condition identifies the record whatever is done to the quasi-identifiers, and the only remedies the challenge forbids.

## Verification tools

Install requirements.txt and requirements-dev.txt, then run `python -m pytest tests`. The organizer's validate_output.py, check_submission.py, and check_dev.py cover the contract and practice data. To reproduce the full check, run `python tools/verify_project.py --toolkit <organizer_toolkit> --output <empty_verification_dir>`. It checks regressions, practice output, repeat-run determinism, changed secrets, input integrity, mutated formats, and strict withholding. On Linux it limits execution to two available CPUs and a 4 GiB address space; start it under `unshare --user --map-root-user --net` to disable networking. Each subprocess has a 900-second timeout. Verification logs and a machine-readable summary are saved in the chosen directory. The practice checker is a rough guide, not the sealed official score. tools/attack_eval.py checks manifest consistency and prints the proxy; it does not simulate hidden attacks.

**Models declaration** None. The runtime uses no LLM, generative model, or pretrained transformer.

See [VERIFICATION.md](VERIFICATION.md) for measured results, remaining limits, and links to the saved check evidence.

## Research explorer

Run `python dashboard/research_server.py` and open http://127.0.0.1:8765 for the landing page. It explains the processing pipeline and links to http://127.0.0.1:8765/dashboard with the labeled synthetic demo. The landing page preserves the supplied design's capsule animation, query entry, serif display type, and four-stage cards. Questions entered there carry into the dashboard. Python's standard library serves the app and aggregate API. Fonts, Three.js, GSAP, and compiled CSS are bundled locally so the interface works offline.

Connect pipeline output with `python dashboard/research_server.py --release <output_dir>`. The adapter reads approved sanitized files through `report.json` and `records.jsonl`, refuses strict-blocked releases, and keeps patient-level data on the server. The server binds to loopback only.

Researchers can filter condition, broad age band, sex, and source file, use a limited rule-based question syntax, inspect distinct-profile breakdowns, save cohorts in browser storage, and download aggregate CSVs. Supported examples include “Show women with diabetes” and “Show age distribution”. Unsupported questions return an error. Applied filters are visible and shareable through the URL.

Clinical coverage currently uses six condition families and selected ICD patterns. Unmatched records are Unclassified. Demographics require recognized structured fields; unsupported formats or ambiguous age bands remain Unknown. A source denotes a file, not necessarily a hospital. Profiles can occur in multiple groups; unlinked records count separately. These descriptive summaries do not estimate treatment effects.

Breakdowns containing any group below five profiles are withheld in full. This is an exploratory disclosure control and does not prevent repeated-query inference. Public hosting of real releases requires a reviewed release policy, authentication where appropriate, rate limits, and controls against differencing queries. The default demo is synthetic and is intended for local review. No publishing is configured.

Verify with `python -m pytest -q`. Frontend files are in `dashboard/research/` and the server is `dashboard/research_server.py`.
