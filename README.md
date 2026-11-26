# StegnoZ

StegnoZ is an offline, CPU-only privacy firewall for **Secret Wards**, Yugaantar DevForge Track 3. It is designed for the challenge's synthetic English, Hindi, and Hinglish hospital exports.

## Run it

Use Python 3.11 or later. Install the pinned cryptography dependency during setup; the runtime makes no network calls. Provide the organizer's key in RAKSHA_SECRET and use separate directories for input and output. The output directory must be empty or absent.

~~~bash
python -m pip install -r requirements.txt
RAKSHA_SECRET=<secret> python main.py --input <input_dir> --output <output_dir>
~~~

The organizer entry point stays in raksha.toml. Privacy settings are in config/policy.yaml. Use --policy to select a different policy file. The run produces UTF-8 sanitized/, report.json, records.jsonl, and an aggregate audit.json.

The default is fail-closed: a missed risk target withholds candidate records, writes counts and diagnostics, and exits with status 1. `--strict-risk` explicitly selects this same behavior. For synthetic challenge scoring, `--allow-risk-miss` explicitly publishes the best candidate even if the target is missed. The competition command in raksha.toml includes that flag because the organizer scores privacy and utility together. A published target miss is never reported as privacy-safe.

## Architecture

1. **Ingestion.** stegnoz/ingest.py recognizes CSV, TSV, JSON, FHIR R4, and notes, sniffs supported encodings, and quarantines malformed or unsupported files. It checks file size before loading the contents and streams the required SHA-256 for oversized inputs.
2. **Detection.** stegnoz/extract.py and stegnoz/sanitize.py combine multilingual schema classification, content voting, context rules, and a run-local dictionary. Clinical numeric fields and protected expressions are handled separately. Labeling can still identify a mistyped Aadhaar value whose checksum fails.
3. **Linkage.** stegnoz/link.py blocks on identifiers and cross-script phonetic keys, scores candidates with Fellegi–Sunter, and checks conflicts before merging. MRN scope comes from a source or FHIR Identifier.system when provided. Shared contact details require corroboration. Pseudonyms and date shifts are keyed from identity evidence. Ambiguous records can be reported with a null patient.
4. **Privacy policy.** stegnoz/privacy.py compares age bands, location granularity, and PIN masking using actual rewritten, verified candidates. Selection and final verification use the same observed signature classes, including separately counted unresolved records. The population multiplier is fixed at one. Candidates cannot win by quarantining additional files. Search stops at the highest feasible utility level, or when the most informative candidate reaches the lower bound imposed by preserved diagnosis codes, event weeks and source facts. Otherwise it checks all 12 policies and picks the lowest risk, breaking ties by generalization utility. This utility credit is not the official clinical utility score. Diagnoses, clinical values and linked date intervals are not sacrificed to force a passing proxy.
5. **Verification and export.** stegnoz/pipeline.py checks residual identifiers. FHIR references are rewritten together and checked for resolution. Unsupported attachment content and sensitive original record locators can cause the whole file to be quarantined. Candidate files are authenticated and encrypted with AES-256-GCM and a fresh, memory-only key per run. Only the selected, authorized release is decrypted for export. The CLI publishes report.json last.

## Security and operating limits

The organizer provides read-only input and an environment secret. For a deployment outside the event sandbox, store source data and releases on encrypted volumes and control key access separately from storage access. The CLI never copies raw input into a staging directory. Decoded records and identity dictionaries exist in process memory, so access to the running process also needs protection. Candidate staging is encrypted even when the final risk target fails. A different authenticated nonce is used on every write; changing a staged file or substituting another file fails authentication. The staging key is separate from RAKSHA_SECRET and is never persisted. Quarantine entries contain a coarse reason and the organizer-required SHA-256. See SECURITY.md for the storage boundary and crash-recovery limitations.

The same input and secret produce identical sanitized/ and records.jsonl on the tested practice run. Randomized internal ciphertext does not affect those exported bytes. Report timing and resource fields vary. Distinct patients can receive the same date offset because the configured range is finite. A changed set of identity evidence can also change a pseudonym. The heuristics can miss unusual identifiers or redact ambiguous terms, and the release risk proxy does not account for all auxiliary knowledge. Multi-patient FHIR bundles retain a whole-document manifest entry with a null patient. The internal 5% threshold is not an official competition threshold; exact signature uniqueness is not measured attacker success. Preserving rare clinical combinations may make that internal target unattainable for a nonempty release.

## Verification tools

Install requirements.txt and requirements-dev.txt, then run `python -m pytest tests`. The organizer's validate_output.py, check_submission.py, and check_dev.py cover the contract and practice data. To reproduce the full check, run `python tools/verify_project.py --toolkit <organizer_toolkit> --output <empty_verification_dir>`. It checks regressions, practice output, repeat-run determinism, changed secrets, input integrity, mutated formats, and strict withholding. On Linux it limits execution to two available CPUs and a 4 GiB address space; start it under `unshare --user --map-root-user --net` to disable networking. Each subprocess has a 900-second timeout. Verification logs and a machine-readable summary are saved in the chosen directory. The practice checker is a rough guide, not the sealed official score. tools/attack_eval.py checks manifest consistency and prints the proxy; it does not simulate hidden attacks.

**Models declaration** None. The runtime uses no LLM, generative model, or pretrained transformer.

See [VERIFICATION.md](VERIFICATION.md) for measured results, remaining limits, and links to the saved check evidence.
