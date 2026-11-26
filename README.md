# StegnoZ

StegnoZ is an offline, CPU-only privacy firewall for **Secret Wards**, Yugaantar DevForge Track 3. It is designed for the challenge's synthetic English, Hindi, and Hinglish hospital exports.

## Run it

Use Python 3.11 or later. The runtime uses only the standard library. Provide the organizer's key in RAKSHA_SECRET and use separate directories for input and output. The output directory must be empty or absent.

~~~bash
python -m pip install -r requirements.txt
RAKSHA_SECRET=<secret> python main.py --input <input_dir> --output <output_dir>
~~~

The organizer entry point stays in raksha.toml. Privacy settings are in config/policy.yaml. Use --policy to select a different policy file. The run produces UTF-8 sanitized/, report.json, records.jsonl, and an aggregate audit.json.

The report records whether the candidate release met the configured risk target. By default a target miss is visible in the console, report, and audit, and the release is published for Track 3 scoring. Use --strict-risk to publish the counts and diagnostics while withholding the candidate records when the target is missed. In strict mode the CLI returns a nonzero exit status on a target miss.

## Architecture

1. **Ingestion.** stegnoz/ingest.py recognizes CSV, TSV, JSON, FHIR R4, and notes, sniffs supported encodings, and quarantines malformed or unsupported files. It checks file size before loading the contents and streams the required SHA-256 for oversized inputs.
2. **Detection.** stegnoz/extract.py and stegnoz/sanitize.py combine multilingual schema classification, content voting, context rules, and a run-local dictionary. Clinical numeric fields and protected expressions are handled separately. Labeling can still identify a mistyped Aadhaar value whose checksum fails.
3. **Linkage.** stegnoz/link.py blocks on identifiers and cross-script phonetic keys, scores candidates with Fellegi–Sunter, and checks conflicts before merging. MRN scope comes from a source or FHIR Identifier.system when provided. Shared contact details require corroboration. Pseudonyms and date shifts are keyed from identity evidence. Ambiguous records can be reported with a null patient.
4. **Privacy policy.** stegnoz/privacy.py chooses age bands, location granularity, and PIN masking. Dates linked to the same identity use the same offset. The final risk proxy uses observed classes from recognized facts in the verified candidate release, including separately counted unresolved records. The organizer's hidden attacker is a separate evaluation.
5. **Verification and export.** stegnoz/pipeline.py checks residual identifiers. FHIR references are rewritten together and checked for resolution. Unsupported attachment content and sensitive original record locators can cause the whole file to be quarantined. The CLI stages verified output privately and publishes report.json last.

## Security and operating limits

The organizer provides read-only input and an environment secret. For a deployment outside the event sandbox, store source data and releases on encrypted volumes and control key access separately from storage access. The CLI never copies raw input into a staging directory. Decoded records and identity dictionaries exist in process memory, so access to the running process also needs protection. Only verified release files are staged. Quarantine entries contain a coarse reason and the organizer-required SHA-256.

The same input and secret produce identical sanitized/ and records.jsonl on the tested practice run. Report timing and resource fields vary. Distinct patients can receive the same date offset because the configured range is finite. A changed set of identity evidence can also change a pseudonym. The heuristics can miss unusual identifiers or redact ambiguous terms, and the release risk proxy does not account for all auxiliary knowledge. Multi-patient FHIR bundles retain a whole-document manifest entry with a null patient.

## Verification tools

Run the local regressions with python -m pytest. Install requirements-dev.txt to run those tests or build the PDF. The organizer's validate_output.py, check_submission.py, and check_dev.py cover the contract and practice data. tools/attack_eval.py --output <output_dir> checks the manifest and prints the recorded risk proxy. It does not simulate the organizer's hidden attacks.

**Models declaration** None. The runtime uses no LLM, generative model, or pretrained transformer.
