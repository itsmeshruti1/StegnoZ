# Verification results and remaining limits

The corrected implementation passed the available organizer practice checks and the local regression suite. This is not an official hidden-dataset score or a guarantee of anonymity. The internal 5% proxy target remains unmet for the practice release.

## Changes verified

| Issue | Resolution |
| --- | --- |
| Inflated population sizes during selection | Population inflation is rejected; observed release groups are used. |
| Selection and final checks measure different things | Both now use the same signatures from actual verified candidate bytes, including unresolved records. |
| No response to a target miss | Search evaluates alternative policies; it reports the preserved-facts lower bound when appropriate. Default CLI runs withhold a failed release. Competition publication requires the explicit `--allow-risk-miss` flag, configured in raksha.toml. |
| Privacy changes can destroy clinical utility | Candidate policies change only age/location/PIN generalization. Diagnoses, clinical values and per-patient date intervals are retained; regression tests and practice probes verify this. |
| Missed patient links | Complete matching phonetic names retain their full-name strength even with common components. Different MRNs with unknown namespaces no longer constitute an automatic conflict; corroborating identity evidence and explicit-namespace conflict checks still apply. |
| Encrypted staging absent | Candidate files use AES-256-GCM with a fresh memory-only run key; tests reject tampering, substituted files and wrong keys. Raw-input and published-output volume encryption still require deployment configuration. |
| Unseen-field failures | Clinician aliases preserve doctor names, and postal-index aliases trigger PIN masking. Both have end-to-end regression coverage. |
| Stress-test annotations invalid after mutation | Derived annotations update file hashes and JSON locators; clinical expectations follow equivalent text/date transformations. Standard FHIR schema keys stay unchanged. Existing destination data is never recursively deleted. |

## Final measured results

The stress dataset is a deterministic transformation of the organizer's practice input: renamed headers/keys, alternate labels and date formats. It is not an independent hidden dataset. No truth or attacker data is loaded by the runtime; those files are used only by development checkers.

| Measure | Organizer practice | Mutated practice |
| --- | ---: | ---: |
| Annotated identifiers left visible | 0 / 3,230 | 0 / 3,230 |
| Planted canaries found | 0 / 4 | 0 / 4 |
| Medical preserve probes retained | 4,855 / 4,855 | 4,855 / 4,855 |
| Pairwise linkage precision | 1.00 | 1.00 |
| Pairwise linkage recall | 0.95 | 0.96 |
| Pairwise F0.5 | 0.99 | 0.99 |
| Pseudonym clusters merging different people | 0 | 0 |
| Unsupported/malformed raw copies | 0 | 0 |
| Sanitized / quarantined input files | 194 / 6 | 194 / 6 |
| Pipeline wall time | 13.58 s | 70.64 s |

The practice run peaked at 44.3 MB RSS and wrote 820 manifest records. The previous documented practice linking recall was 0.87; the new result is 0.95 without a reported precision loss. The checker rounds linkage metrics to two decimals and is explicitly a rough guide, not the official scorer.

## Verification environment and evidence

- Python 3.14.4 on Ubuntu through WSL2, kernel 6.18.33.2, glibc 2.43.
- A clean source copy and data copy on Linux temporary storage, outside the Windows-mounted filesystem.
- Linux network namespace isolation (`unshare --user --map-root-user --net`); two CPU cores; 4 GiB per-process address-space limit inherited by children; 900-second subprocess timeouts. This is not the organizer's full filesystem/process sandbox or a process-tree RSS watchdog.
- **28 regression tests passed**, covering clinical intervals, ages, linkage conflicts, hidden identifiers, FHIR, candidate selection, encryption, withholding and mutation annotations.
- The same **28 tests passed on Windows Python 3.15** in 10.02 seconds; see [Windows test output](verification/windows-regressions.log).
- Organizer **CONTRACT OK** on both datasets.
- Organizer **READY TO SUBMIT** after three runs: identical sanitized files and manifest with the same secret, changed output with a different secret, no secret in output/logs, unchanged input.
- Default strict mode exited 1 as expected and withheld the failed practice release.
- The rebuilt brief was rendered and visually inspected as two pages.

Evidence: [summary](verification/summary.json), [regressions](verification/regressions.log), [contract](verification/contract.log), [submission](verification/submission.log), [practice](verification/practice_check.log), [stress](verification/mutated_check.log), and [verified source hashes](verification/source-sha256.json). The archive builder verifies that the runtime, configuration, test and tool files match the exact source copy used for the final Linux run, and checks their archived bytes again.

## Limits that remain

The practice proxy is **58.72%**, down from the previously documented 65.65%, but still above the internal 5% target. Its preserved diagnosis-code/event-week/source signatures impose the same lower bound under the current age/location/PIN policy lattice. Merely widening those fields cannot solve it. This is exact observed-class uniqueness, not the probability that the organizer's attacker identifies someone. The target is an internal setting, not a published competition cutoff.

Normal CLI execution therefore blocks this release. The challenge entry point deliberately publishes the best candidate with a visible target-miss report, so the organizer can assess privacy and retained utility together. Meeting the internal target with a useful nonempty release would require a different release design or suppression with explicit utility loss; this version does not pretend that deleting medical information is a successful fix.

The stress run exceeds the scoring document's 60-second full-credit speed threshold, although it is well below the 900-second hard limit. Larger hidden datasets may take longer. Missed/ambiguous links remain; observed precision on practice data does not guarantee precision on unseen identities. The sealed attacks, hidden datasets, public-repository eligibility and actual storage-volume encryption remain unverified. See [SECURITY.md](SECURITY.md) for the deployment boundary.

## Reproduce

Install requirements.txt and requirements-dev.txt in a dedicated environment, obtain the organizer toolkit, then run:

```sh
python -m pytest tests
python tools/verify_project.py --toolkit /path/to/Secret-Wards-ToolKit --output /new/empty/directory
```

On Linux, prefix the second command with `unshare --user --map-root-user --net` to repeat offline isolation. The verifier writes logs and a summary and fails if practice/stress checks leak an annotated identifier or canary, lose medical probes, or report precision below 1.00. Neither this check nor the included artifact contains the sealed official evaluator.
