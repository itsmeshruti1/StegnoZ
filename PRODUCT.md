# StegnoZ Research

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Researchers exploring cohorts and exporting aggregate results from the existing RakshaMed privacy pipeline. The user explicitly prioritized cohort exploration and aggregate exports.

## Product Purpose

Make sanitized hospital releases explorable through a browser. Keep provenance, interpretation, and supported coverage visible.

## Repository state

Updated 27 November 2026 from the local checkout at `C:\Users\ASUS\Desktop\stegnoZ\RakshaMed`.

The research website is integrated with the StegnoZ working tree as a local-only interface. It remains separate from the organizer execution command, has not been deployed, and must be committed and pushed before it appears in the public repository.

StegnoZ is both the Python privacy pipeline and the browser-facing research product.

## Implemented surfaces

| Surface | Entry point | Current behavior |
| --- | --- | --- |
| Landing page | `/` | Introduces the product, explains the workflow, displays an animated data sphere, and links to the dashboard. Motion can be paused and respects reduced-motion preferences. |
| Cohort preview | Landing-page condition selector | Calls the aggregate API and opens the selected condition in the dashboard. Labels synthetic demo data. |
| Research explorer | `/dashboard` | Filters by condition, age band, sex, and source file. Shows distinct-profile counts, condition and age charts, and selectable breakdown tables. |
| Saved cohorts | `/dashboard#saved` | Stores up to 20 cohort definitions in browser local storage and supports reopening and removal. |
| Methodology | `/dashboard#methods` | Explains provenance, supported coverage, counting rules, suppression, and interpretation limits. |
| CSV export | Research explorer export action | Downloads the current filters, dataset mode, counting method, and releasable aggregate breakdowns. |
| Privacy audit report | `dashboard/build_dashboard.py` | Generates the existing static release audit from `report.json` and `audit.json`. |

Dashboard filters are reflected in the URL. Earlier root URLs with query parameters redirect to `/dashboard` with those parameters. The dashboard's home link returns to the landing page.

## Stack and entry points

Python 3.11+ and the standard library serve the website and aggregate API. The frontend uses HTML, CSS, JavaScript, and locally bundled GSAP 3.15.0. Manrope loads optionally from Google Fonts with a local system-font fallback. The privacy pipeline uses no LLM or pretrained transformer.

| Component | Location |
| --- | --- |
| Pipeline entry and evaluation contract | `main.py`, `raksha.toml` |
| Privacy pipeline modules | `stegnoz/` |
| Privacy configuration | `config/policy.yaml` |
| Research server, release adapter, aggregation | `dashboard/research_server.py` |
| Landing page | `dashboard/research/landing.html`, `reference.css`, `reference-landing.js` |
| Dashboard | `dashboard/research/index.html`, `reference-dashboard.css`, `reference-dashboard.js` |
| Animation library | `dashboard/research/gsap.min.js` |
| Regression tests | `tests/test_core.py`, `tests/test_release.py`, `tests/test_research.py` |
| Visual system | `DESIGN.md` |

Run the demo from the repository root with `python -m dashboard.research_server`, then open `http://127.0.0.1:8765/`. Connect a pipeline release with `python -m dashboard.research_server --release <output_dir>`. An optional `--port` changes the default port. The server binds to `127.0.0.1`.

The browser reads dataset metadata from `GET /api/catalog` and obtains aggregates through `POST /api/query`. The server exposes an explicit list of frontend assets.

## Capabilities and Constraints

The deterministic synthetic demo contains 960 observations representing 480 fictional profiles across four labeled sources. Release mode reads approved sanitized files through `report.json` and `records.jsonl`, checks resolved paths against the sanitized directory, and rejects releases marked `strict_blocked`. The adapter exposes the recorded risk-target result but does not reject every release that missed its risk target.

The current condition dictionary covers diabetes, hypertension, dengue, asthma, tuberculosis, and typhoid using English text and selected ICD patterns. Other records are Unclassified. Demographics come from recognized structured fields. Unsupported or ambiguous values remain Unknown. A source label represents a file. Text and FHIR normalization have limited clinical coverage.

Question input uses a small rule-based grammar. Examples include “Show women with diabetes” and “Show age distribution”. Supported questions become explicit filters. Unsupported questions return an error. The explorer does not provide arbitrary medical question answering or treatment-effect estimates.

Counts represent distinct linked profiles within each group. Unresolved records count separately. Profiles may appear in multiple groups, so group totals can exceed the cohort total. Cohorts containing one to four profiles have their exact count withheld. A breakdown containing any group below five profiles is withheld in full, including in CSV exports.

Public use of real releases remains pending additional disclosure controls. The small-group rule does not prevent repeated-query inference. Authentication, access governance, rate limiting, and production hosting are not implemented. Saved cohorts belong to the browser rather than a user account. The existing release pipeline remains responsible for sanitization and release verification.

## Verification

`python -m pytest -q` covers pipeline and research regressions. Research tests cover demo counts, question filters, unsupported queries, overlapping groups, small-cell suppression, manifest path restrictions, strict-blocked releases, ambiguous age bands, HTTP routes, API responses, and browser security headers.

Prior Playwright checks during implementation covered landing-to-dashboard navigation, selected-cohort handoff, return navigation, legacy query redirects, research queries, saved cohorts, CSV downloads, error and empty states, motion controls, reduced motion, and overflow at 320, 390, 768, and 1440 pixels. Those browser checks were not rerun for this documentation-only update. Captures and test exports are local artifacts under ignored `output/playwright/`.

A prior practice-data run processed 200 files and produced a release that the adapter could load. That run missed the pipeline risk target. It was used for local integration validation and does not establish public-release readiness.

## Evidence on Hand

README.md describes the existing pipeline. The supplied Secret Wards problem statement specifies synthetic multilingual hospital records. A local organizer practice dataset is available for validation. Demo observations are generated and labeled synthetic.

## Implementation assumptions

Use Python standard-library serving and plain HTML/CSS/JavaScript to fit the existing project. This was an implementation choice. Source files are labeled generically and never assumed to represent individual hospitals.
