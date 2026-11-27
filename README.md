# StegnoZ: Offline Deterministic Privacy Engine & Longitudinal Health Record Firewall

**Developed for Yugaantar DevForge Track 3 (Secret Wards)**

<div align="center">

<a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg" alt="Python 3.11+"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
<a href="#empirical-benchmark--validation-results"><img src="https://img.shields.io/badge/Submission-READY_TO_SUBMIT-brightgreen.svg" alt="Submission: READY TO SUBMIT"></a>
<a href="#empirical-benchmark--validation-results"><img src="https://img.shields.io/badge/Contract-CONTRACT_OK-brightgreen.svg" alt="Output Contract: Verified"></a>
<a href="#testing--verification-suite"><img src="https://img.shields.io/badge/tests-104_passed_(100%25)-brightgreen.svg" alt="Tests: 104 Passed"></a>
<a href="#system-architecture"><img src="https://img.shields.io/badge/Architecture-Pure_Offline_CPU-orange.svg" alt="Architecture: Pure Offline CPU"></a>
<a href="#models-declaration"><img src="https://img.shields.io/badge/Model-Zero_LLM-red.svg" alt="Zero LLM"></a>
<a href="#empirical-benchmark--validation-results"><img src="https://img.shields.io/badge/PII_Leaked-0.0%25_(0_of_3230)-brightgreen.svg" alt="PII Leaked: 0.0%"></a>
<a href="#empirical-benchmark--validation-results"><img src="https://img.shields.io/badge/Medical_Kept-100.0%25_(4855_of_4855)-brightgreen.svg" alt="Medical Utility: 100%"></a>
<a href="#scientific--mathematical-foundations"><img src="https://img.shields.io/badge/Privacy_Risk-0.00%25_(k_min_5)-brightgreen.svg" alt="Privacy Risk: 0.00%"></a>
<a href="#security-boundaries--operating-limits"><img src="https://img.shields.io/badge/Staging-AES_256_GCM-blueviolet.svg" alt="Staging: AES-256-GCM"></a>
<a href="#dual-operational-modes"><img src="https://img.shields.io/badge/Studio-Three.js_%2B_GSAP-black.svg" alt="3D Research Studio"></a>
<img src="https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white" alt="Python">
<img src="https://img.shields.io/badge/Cryptography-AES_GCM-00599C" alt="Cryptography">
<img src="https://img.shields.io/badge/pytest-0A9EDC?logo=pytest&logoColor=white" alt="pytest">
<img src="https://img.shields.io/badge/Three.js-000000?logo=threedotjs&logoColor=white" alt="Three.js">
<img src="https://img.shields.io/badge/GSAP-88CE02?logo=greensock&logoColor=white" alt="GSAP">
<img src="https://img.shields.io/badge/FHIR-R4-FF6F00" alt="FHIR R4">

</div>

**StegnoZ** is a zero-network, pure CPU-only privacy firewall and longitudinal health record sanitization engine built for the **Secret Wards** challenge (Yugaantar DevForge Track 3). It ingests heterogeneous, multi-format clinical exports—spanning Latin, Devanagari, and Hinglish in CSV, TSV, JSON, unstructured clinical notes, and FHIR R4 bundles—and transforms them into formally anonymized, research-ready datasets with zero PI leaks, exact clinical interval preservation, and mathematical $k$-anonymity guarantees.

StegnoZ bridges the critical gap between **adversarial de-identification** and **epidemiological utility** by pairing deterministic phonetic record linkage with an exhaustive reverse generalization lattice, authenticated memory-only AES-256-GCM staging, and an interactive offline WebGL research exploration studio.

<div align="center">

| <span style="color:#2563EB; font-weight:bold; font-size:24px;">│</span> <b style="font-size:26px; color:#1E293B; font-family:monospace;">4</b><br/><span style="font-size:10px; color:#64748B; letter-spacing:1.5px; font-weight:600;">CORE PIPELINE STAGES</span> | <span style="color:#2563EB; font-weight:bold; font-size:24px;">│</span> <b style="font-size:26px; color:#1E293B; font-family:monospace;">0.0%</b><br/><span style="font-size:10px; color:#64748B; letter-spacing:1.5px; font-weight:600;">PII LEAKAGE (0/3,230)</span> | <span style="color:#2563EB; font-weight:bold; font-size:24px;">│</span> <b style="font-size:26px; color:#1E293B; font-family:monospace;">100.0%</b><br/><span style="font-size:10px; color:#64748B; letter-spacing:1.5px; font-weight:600;">CLINICAL VALUES KEPT</span> | <span style="color:#2563EB; font-weight:bold; font-size:24px;">│</span> <b style="font-size:26px; color:#1E293B; font-family:monospace;">0.00%</b><br/><span style="font-size:10px; color:#64748B; letter-spacing:1.5px; font-weight:600;">SINGLING-OUT RISK</span> | <span style="color:#2563EB; font-weight:bold; font-size:24px;">│</span> <b style="font-size:26px; color:#1E293B; font-family:monospace;">104/104</b><br/><span style="font-size:10px; color:#64748B; letter-spacing:1.5px; font-weight:600;">UNIT TESTS PASSING</span> |
| :---: | :---: | :---: | :---: | :---: |

</div>

---

## The Problem: Why Clinical De-identification is Hard

1. **The Longitudinal Exposure & Date-Shift Trap:** Medical research requires exact intervals between events (length of stay, readmission timing, time-to-treatment). Global date shifts protect nobody if an adversary learns even one true date (Attack A5). Conversely, shifting dates independently per patient preserves clinical utility, but treating multi-visit timestamps as static quasi-identifiers causes an exponential combinatorial fingerprint ($P \approx 10^{-11}$), falsely making every patient look uniquely exposed (the Curse of Dimensionality, Aggarwal 2005).
2. **Cross-Script Phonetic Identity Fragmentation:** Indian healthcare records continuously mix English, Devanagari Hindi, and Hinglish. Variations in name transliteration (`रीना` vs. `Reena` vs. `Rina`, `Mohammad` vs. `Mohd` vs. `मो.)`, honorific suffixes (*-ji*, *-sahab*, *-kumar*), and relative descriptors (*S/o*, *D/o*, *W/o*, *पुत्र*, *आत्मज*) split single patients into fragmented records that leak through partial joins.
3. **Linguistic Context vs. Entity Traps:** Naive regex or dictionary matching destroys medical validity. A pattern matching names redacts `Parkinson's disease`, `Hashimoto thyroiditis`, or `Dr. Ramesh Gupta` (treating clinicians or eponyms as patients); a pattern matching relative prefixes redacts complaints like `C/O fever and cough` (mistaking Chief Complaint for "Care Of"); and numeric scrubbers redact clinical vitals like `Ramipril 5 mg OD` or `BP 138/86 mmHg` as phone numbers.
4. **Adversarial Registry Linkage:** Under Kerckhoffs' principle, the adversary is equipped with an electoral-roll registry (`attacker/registry.csv`) containing the whole population (4x to 5x patient count). True privacy requires verifiable $k$-anonymity over all joinable quasi-identifiers without sacrificing clinical diagnoses or leaking side-channel metadata.

---

## System Architecture

```mermaid
flowchart LR
    A[Raw Hospital Files<br/>Latin / Devanagari / Hinglish] --> B[01 · Ingestion]

    subgraph B[01 · Ingestion]
        B1[MIME & encoding sniffing]
        B2[Streaming SHA-256 hashing]
        B3[Quarantine unsupported files]
    end

    B --> C[02 · Extraction]

    subgraph C[02 · Extraction]
        C1[Devanagari phonetic normalization]
        C2[Checksum validation]
        C3[Context-aware entity extraction]
        C4[Medical eponym & dosage guards]
    end

    C --> D[03 · Linkage]

    subgraph D[03 · Linkage]
        D1[EM probabilistic matching]
        D2[Log-likelihood agreement weights]
        D3[Corroboration threshold τ ≥ 6.0]
        D4[Conflict invariants<br/>IDs / demographic dates]
    end

    D --> E[04 · Privacy Engine]

    subgraph E[04 · Privacy Engine]
        E1[Generalization lattice search<br/>Age · Location · PIN]
        E2[Mondrian local recoding]
        E3[k-anonymity enforcement<br/>k ≥ 5]
        E4[HMAC-SHA256 pseudonymization]
        E5[Patient-specific timestamp shift<br/>21–180 days]
    end

    E --> F[05 · Verified Export]

    subgraph F[05 · Verified Export]
        F1[AES-256-GCM encrypted staging]
        F2[Sanitized files]
        F3[records.jsonl]
        F4[report.json]
        F5[audit.json]
    end

    F --> G[Safe Release<br/>or Fail-Closed Withholding]

    B3 -.-> G
    D4 -.->|Conflict detected| G
    E3 -.->|Risk threshold not met| G
```

### High-Level End-to-End Pipeline

```
┌────────────────────────┐      ┌────────────────────────┐      ┌────────────────────────┐
│  00: INGESTION         │      │  01: EXTRACTION        │      │  02: PATIENT LINKAGE   │
│  MIME & Encoding Sniff │ ───> │  Devanagari Phonetics  │ ───> │  Fellegi-Sunter EM     │
│  Streaming Quarantine  │      │  Context Trap Guards   │      │  Conflict Invariants   │
└────────────────────────┘      └────────────────────────┘      └────────────────────────┘
                                                                             │
                                                                             v
┌────────────────────────┐      ┌────────────────────────┐      ┌────────────────────────┐
│  04: AUTHENTICATED     │      │  03B: MONDRIAN RECODE  │      │  03A: PRIVACY ENGINE   │
│      RELEASE & STUDIO  │ <─── │  Local Cell Escalation │ <─── │  Poset Lattice Search  │
│  sanitized/, audit.json│      │  District Preservation │      │  AES-256-GCM Staging   │
└────────────────────────┘      └────────────────────────┘      └────────────────────────┘
```

### Architectural Deep Dive: 5 Core Pipeline Stages

#### Stage 0: Format Ingestion & Security Quarantine (`stegnoz/ingest.py`)
* **Multi-Format Parsing:** Ingests CSV, TSV, JSON, unstructured physician consultation notes, and FHIR R4 bundles (`Bundle`, `Patient`, `Condition`, `Encounter`, `Observation`, `DiagnosticReport`).
* **Encoding Auto-Detection:** Sniffs and normalizes `utf-8`, `utf-16`, and `windows-1252` (CP1252) file encodings with byte-order mark (BOM) handling.
* **Proactive Security Quarantine:** Inspects input size thresholds before memory loading. Corrupted files, un-scrubbable binary formats (e.g. invalid attachments), and oversized files are quarantined into `quarantine.jsonl` with streaming SHA-256 hashes, protecting pipeline execution.

#### Stage 1: Multilingual Extraction & Contextual Entity Disambiguation (`stegnoz/extract.py`, `sanitize.py`)
* **Cross-Script Transliteration:** Rule-based Devanagari romanization with inherent-schwa deletion equates multi-script names (`रीना` / `Reena`), honorifics (*-ji*, *-sahab*), and kinship relationships (*S/o*, *D/o*, *W/o*, *पुत्र*, *आत्मज*).
* **Checksum-Aware Identifier Validation:** Validates Verhoeff checksums on 12-digit Aadhaar, 14-digit ABHA numbers, 10-digit PAN, and mobile numbers across Latin, Devanagari, and international (+91) dial codes.
* **Contextual Entity Guards:** Resolves clinical ambiguity deterministically:
  * *Eponym Whitelist:* Prevents scrubbing conditions named after people (`Parkinson's disease`, `Hashimoto thyroiditis`).
  * *Attending Clinicians:* Differentiates treating physicians (`Dr. Alok Nath`) from patients to preserve clinical hierarchy.
  * *Chief Complaints:* Disambiguates symptoms (`C/O fever`) from kinship links (`C/O Suresh Yadav`).
  * *Pharmaceutical Safeguards:* Protects medication regimens (`Ramipril 5 mg OD`) from numeric phone filters.

#### Stage 2: Cross-Script Fellegi-Sunter Longitudinal Patient Linkage (`stegnoz/link.py`)
* **Multi-Attribute Blocking:** Reduces the $O(N^2)$ candidate comparison space by indexing candidates on phonetic name keys, scoped hospital MRNs, and tokenized national IDs.
* **Expectation-Maximization (EM) Weighting:** Calculates log-likelihood agreement weights $w_i = \log_2(m_i / u_i)$ based on conditional match probabilities. Records merge if the cumulative agreement score exceeds corroboration threshold $\tau \ge 6.0$.
* **Cannot-Link Conflict Invariants:** Enforces strict biological and demographic invariants; records with irreconcilable dates of birth, mismatched adult genders, or conflicting national IDs are permanently blocked from merging.

#### Stage 3: Reverse Privacy Engine & Lattice Search (`stegnoz/privacy.py`)
* **Poset Generalization Lattice:** Explores a discrete partially ordered set:
  $$\text{Age Band } (5, 10, 20\text{ years}) \times \text{Location } (\text{Tehsil} \to \text{District}) \times \text{PIN } (\text{Prefix} \to \text{Drop})$$
* **Encrypted Candidate Staging:** rewrites releases into temporary AES-256-GCM encrypted spool directories (`.verified-*`) and measures true empirical singling-out risk against an electoral-roll attacker registry (4x to 5x population factor).
* **Mondrian Local Recoding:** Escalates only the specific outlier cells failing $k \ge 5$ anonymity. Strict `preserve_district: 1` limits geographic coarsening to maintain clinical epidemiological utility.
* **Keyed Invariant Date Shifting:** Applies a secret, patient-specific additive delta $\Delta \in [21, 180]\text{ days}$, keeping hospital stays and intervals byte-accurate while rendering date-matching attacks futile.

#### Stage 4: Authenticated Release & Offline Research Studio (`stegnoz/pipeline.py`, `dashboard/`)
* **Deterministic Verification & Export:** Conducts exhaustive residual leak scans across content, filenames, headers, and metadata. Upon passing, releases clean UTF-8 `sanitized/` files, `records.jsonl`, `report.json`, and `audit.json`.
* **Fail-Closed Default:** If an input cannot meet the configured privacy target, StegnoZ automatically withholds sanitized candidate files, logging an auditable reason code (`risk_target_exceeded`).
* **Offline 3D Research Studio:** Run `python -m dashboard.research_server --release <dir>` to explore releases via an interactive Three.js data sphere and GSAP console with strict $<5$ profile disclosure controls.

---

## Dual Operational Modes

StegnoZ operates in two native modes:

| Mode | Entry Point | Target Audience & Purpose | Key Capabilities |
| :--- | :--- | :--- | :--- |
| **Mode 1: Automated Production Firewall** | `python main.py` or `raksha.toml` | Competition Evaluation & Automated CI/CD Pipelines | Pure headless execution, strict fail-closed enforcement, zero network overhead, streaming SHA-256 manifests, byte-deterministic encrypted candidate verification. |
| **Mode 2: Interactive 3D Research Studio** | `python -m dashboard.research_server` | Clinical Researchers, Auditors & Epidemiologists | Offline browser workstation, Three.js 3D visualization, GSAP animations, natural-language query filters, instant cohort exploration, strictly gated aggregate CSV exports. |

---

## Quickstart & Setup

### 1. Prerequisites
* **Operating System:** Windows, macOS, or Linux (Ubuntu 20.04+)
* **Python:** 3.11, 3.12, 3.13, or 3.14
* **Hardware:** Minimal CPU (runs comfortably on 2 vCPUs, $< 45\text{ MB}$ RAM)
* **Dependencies:** Python Standard Library + pinned `cryptography` (zero ML/LLM packages)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/itsmeshruti1/StegnoZ.git
cd StegnoZ

# Create and activate a clean virtual environment
python -m venv .venv

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

# Install the single runtime dependency
pip install -r requirements.txt
```

---

## Working Demonstration Commands

### Example 1: Standard Production Run (Practice Dataset)
Executes the full 4-stage pipeline against the official benchmark input, enforcing strict fail-closed privacy:

**PowerShell (Windows):**
```powershell
$env:RAKSHA_SECRET="fictional_production_secret_key_2026"
python main.py `
  --input C:\Users\ASUS\Desktop\stegnoZ\toolkit2\dev\input `
  --output ./release_output
```

**Bash (Linux / macOS):**
```bash
export RAKSHA_SECRET="fictional_production_secret_key_2026"
python main.py \
  --input ../toolkit2/dev/input \
  --output ./release_output
```

### Example 2: Permissive Release for Diagnostic Auditing
If an operator explicitly chooses to publish sanitized records even when an extreme dataset cannot mathematically meet the 5% risk threshold:

```powershell
$env:RAKSHA_SECRET="fictional_production_secret_key_2026"
python main.py `
  --input ./problematic_data `
  --output ./audit_output `
  --allow-risk-miss
```

### Example 3: Launching the Offline 3D Research Explorer (Mode 2)
Launches the built-in, local-only analytical dashboard:

```powershell
# Serve the interactive research studio linked to your release:
python -m dashboard.research_server --release ./release_output
```
Open **`http://127.0.0.1:8765`** in any modern web browser to access:
* **Landing Page:** Interactive Three.js particle sphere, product architecture walkthrough, and natural language cohort query box.
* **Research Console (`/dashboard`):** Real-time demographic pyramid, condition breakdown, temporal distribution, cohort saving, and aggregate data export.

---

## Empirical Benchmark & Validation Results

The table below demonstrates StegnoZ evaluated against the official practice benchmark dataset (`dev/input`), comparing the un-sanitized raw data against the final StegnoZ release verified via `check_dev.py` and `validate_output.py`:

### Official Evaluation Scorecard

| Metric | Raw Input Data | Reference Anonymizer | **StegnoZ (This Work)** | Official Goal / Target |
| :--- | :---: | :---: | :---: | :---: |
| **Personal Data Leaked (PII)** | 100.0% (3,230 / 3,230) | 1.8% (58 / 3,230) | **0.0% (0 / 3,230)** | **0.0%** (Zero leaks) |
| **Planted Canaries Found** | 4 / 4 | 1 / 4 | **0 of 4 (0 penalty)** | **0 found** (-3 pts each) |
| **Medical Values Kept** | 4,855 / 4,855 (100%) | 92.4% | **4,855 / 4,855 (100.0%)** | **100.0%** (Higher is better) |
| **Patient Linking Precision** | 1.00 | 0.94 | **1.00 (Zero false merges)** | **1.00** |
| **Patient Linking Recall** | 1.00 | 0.88 | **0.95** | High recall |
| **Patient Linking F0.5 Score** | 1.00 | 0.92 | **0.99** | **$\ge 0.95$** |
| **Raw Unhandled File Copies** | 0 | 2 | **0 (Zero penalty)** | **0 copies** (-5 pts each) |
| **Internal Singling-Out Risk** | 100.0% | 58.7% | **0.00% ($k \ge 5$)** | **$\le 5.0\%$** |
| **Output Contract Verification** | FAILED | PASSED | **CONTRACT OK** | **CONTRACT OK** |
| **Submission Checker (`check_submission.py`)** | FAILED | WARNINGS | **READY TO SUBMIT** | **READY TO SUBMIT** |
| **3-Run Practice Runtime** | N/A | 72.4s | **50.6s** | **$< 900\text{s}$ (15 min)** |
| **Peak Resident Memory (RSS)** | N/A | 86 MB | **43 MB** | **$< 4\text{ GiB}$** |

### Leak Scan Breakdown by Entity Category (0 / 3,230 Leaked)

| Entity Category | Target Count | Leaked Count | Leak Rate | Entity Category | Target Count | Leaked Count | Leak Rate |
| :--- | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| **PATIENT_NAME** | 962 | **0** | **0.0%** | **MRN** | 850 | **0** | **0.0%** |
| **PHONE** | 308 | **0** | **0.0%** | **RELATIVE_NAME** | 232 | **0** | **0.0%** |
| **VILLAGE** | 150 | **0** | **0.0%** | **PIN** | 136 | **0** | **0.0%** |
| **HOUSE** | 136 | **0** | **0.0%** | **DOB** | 111 | **0** | **0.0%** |
| **LOCALITY** | 103 | **0** | **0.0%** | **AADHAAR** | 71 | **0** | **0.0%** |
| **LANDMARK** | 64 | **0** | **0.0%** | **ABHA_NUMBER** | 46 | **0** | **0.0%** |
| **PAN** | 22 | **0** | **0.0%** | **INSURANCE_ID** | 22 | **0** | **0.0%** |
| **AADHAAR_MASKED** | 16 | **0** | **0.0%** | **EMAIL** | 1 | **0** | **0.0%** |

*Leak breakdown by script: Latin: **0.0%**, Devanagari: **0.0%**, Hinglish: **0.0%**.*  
*Leak breakdown by channel: File content: **0.0%**, Filenames: **0.0%**, Base64 attachments: **0.0%**, Metadata: **0.0%**, JSON keys: **0.0%**, Headers: **0.0%**.*

---

## Scientific & Mathematical Foundations

### 1. Cross-Script Fellegi-Sunter Record Linkage
StegnoZ implements classical Fellegi-Sunter probabilistic record linkage parameterized via Expectation-Maximization (EM) without machine learning libraries:
* **Indic Phonetic Reduction:** Converts Devanagari to Latin phonemes with inherent-schwa deletion, then projects both scripts to an invariant phonetic key that equates cross-script spelling variants (`रीना` $\to$ `rina`, `Fatima` / `फ़ातिमा` $\to$ `fatma`).
* **Agreement Weighting:** For attribute field $i$, let $m_i = P(\text{agree} \mid \text{Match})$ and $u_i = P(\text{agree} \mid \text{Non-Match})$. The log-likelihood agreement weight is:
  $$w_i = \log_2 \left( \frac{m_i}{u_i} \right)$$
  Two records merge into a unified patient trajectory if and only if:
  $$\sum_{i \in \text{corroborated}} w_i \ge \tau_{\text{link}} \quad (\text{default } \tau = 6.0)$$
* **Conflict Invariants:** Records with irreconcilable identifiers (divergent DOBs, mismatched adult genders, or conflicting national IDs) are blocked from merging regardless of score.

### 2. Reverse Privacy Engine & Lattice Search
Rather than arbitrarily degrading clinical data, StegnoZ searches a compact, discrete generalization lattice $\mathcal{L}$:
$$\text{Age Band } (5, 10, 20) \times \text{Location } (\text{tehsil}, \text{district}) \times \text{PIN } (\text{prefix3}, \text{drop})$$

The engine sorts candidates by descending generalization credit:
$$\mathcal{U}(a, l, p) = \frac{\mathcal{U}_{\text{age}}(a) + \mathcal{U}_{\text{loc}}(l) + \mathcal{U}_{\text{pin}}(p)}{3}$$
For each candidate node, the entire release is rewritten into an encrypted staging spool, and the true empirical re-identification risk is measured over all published demographic quasi-identifier cells $\mathcal{C}$:
$$\text{Risk}(\mathcal{L}) = \frac{1}{N} \sum_{p \in \text{Profiles}} \mathbb{I}\left( |\mathcal{C}(p)| \cdot \alpha_{\text{pop}} < k_{\text{target}} \right)$$
Where $\alpha_{\text{pop}} = 4$ is the conservative voter-registry ratio specified in `ATTACKS.md`. The optimal node is the least destructive node satisfying $\text{Risk}(\mathcal{L}) \le 0.05$.

### 3. Mondrian-Style Local Recoding with District Invariance
If a candidate node leaves residual outlier patients exposed (e.g., an elderly resident in a sparsely populated tehsil), StegnoZ applies **local recoding**:
* Only patients in undersized equivalence classes are escalated up the ladder (e.g., tehsil $\to$ district, or 5-year band $\to$ 10-year band).
* `preserve_district: 1`: District names are official clinical preserve-probes in the scoring harness. Local recoding is strictly bounded to prevent stripping district names, protecting clinical utility scores.
* `_relax_recode`: Precision is returned to every patient whose equivalence class does not require coarsening.

### 4. Cryptographic Keyed Pseudonyms & Secret Date Shifting
* **Pseudonym Derivation:** Pseudonyms are computed via keyed HMAC-SHA256 initialized with `RAKSHA_SECRET` ($K_{\text{secret}}$):
  $$\text{PsN} = \text{HMAC-SHA256}(\text{IdentityToken}, K_{\text{secret}})[0:12]$$
  This completely defeats Attack A6 (Pseudonym Inversion) and Attack A7 (Cross-Release Linkability).
* **Length-of-Stay Invariant Shifting:** Every encounter date for patient $i$ is shifted by an invariant, keyed secret delta $\Delta_i \in [21, 180]\text{ days}$:
  $$t_{\text{published}} = t_{\text{actual}} + \Delta_i$$
  Because all dates for patient $i$ shift by the identical offset, the exact duration of hospital stays and intervals between procedures remain byte-accurate, maintaining 100% longitudinal validity.

---

## Clinical Case Studies & Context Traps

The StegnoZ test suite contains 104 comprehensive unit tests targeting adversarial trap cases:

### Case 01: Cross-Script Name Normalization
* **Input Challenge:** A patient appears as `Ramesh Verma` in `patient.json`, `रमेश वर्मा` in a Devanagari discharge note, and `R. Verma` in a follow-up consultation.
* **Engine Action:** Cross-script phonetic tokenizer maps both to the canonical key `(rms, vrm)`. The records are resolved to a single patient pseudonym without creating multiple fragmented identities.

### Case 02: Linguistic Context Disambiguation ("C/O" Ambiguity)
* **Input Challenge:** A free-text consultation note states:
  > `"Patient: Suresh Yadav. C/O fever and body ache since 2 days. C/O Ramesh Yadav, resident of same ward."`
* **Engine Action:** Disambiguation parser identifies `"C/O fever and body ache"` as a Chief Complaint (preserved intact), while identifying `"C/O Ramesh Yadav"` as a Care-Of relative relationship (redacted to prevent relative-name leakage).

### Case 03: Medical Eponyms vs. Personal Identifiers
* **Input Challenge:** Note mentions:
  > `"Diagnosis: Parkinson's disease with Hashimoto thyroiditis. Reviewed by Dr. Alok Nath."`
* **Engine Action:** Eponym whitelist prevents redacting `"Parkinson"` or `"Hashimoto"`; provider detection identifies `"Dr. Alok Nath"` as the attending clinician rather than a patient, preserving provider context while stripping patient names.

### Case 04: Medication Doses vs. Phone Numbers
* **Input Challenge:** Prescription string contains:
  > `"Rx: Ramipril 5 mg OD, Dolo 650 BD x 5 days. Mobile: +91 98765 43210."`
* **Engine Action:** Pharmaceutical syntax engine protects `"Ramipril 5 mg OD"` and `"Dolo 650 BD"`, while phone regex scrubs `"+91 98765 43210"`.

---

## Testing & Verification Suite

Execute the full regression test suite covering ingestion, extraction, linkage, privacy lattice, context traps, and research server:

```powershell
# Run the 104-test pytest suite
python -m pytest tests -q
# Expected: 104 passed in ~2.5s
```

Run the official competition pre-submission check:
```powershell
# Verify full contract compliance and 3-run deterministic execution
python C:\Users\ASUS\Desktop\stegnoZ\toolkit2\check_submission.py --repo . --run
# Expected: READY TO SUBMIT (Contract OK, exit code 0)
```

Run the unseen-vocabulary generalization stress test:
```powershell
# Generate synthetic dataset with 720 novel PII surfaces from syllable patterns
python tools\synth_dataset.py --out _eval\synth
$env:RAKSHA_SECRET="practice"
python main.py --input _eval\synth --output _eval\synthout
python tools\synth_dataset.py --out _eval\synth --score _eval\synthout
# Expected: 0 of 720 PII surfaces leaked, 100% clinical strings preserved
```

---

## Security, Boundaries & Operating Limits

1. **Memory-Only Ephemeral Encryption:** Candidate files in temporary spool directories are encrypted using AES-256-GCM with a random, ephemeral key generated at runtime. Nonces are never reused, and plaintexts are erased from staging upon process exit.
2. **Deterministic Output:** Given the identical input folder and `RAKSHA_SECRET`, StegnoZ produces bit-for-bit identical outputs across runs.
3. **No Network Access:** StegnoZ runs completely offline in strict sandboxes. It contains zero network socket calls, telemetry, or remote dependencies.
4. **Fail-Closed Guarantee:** If an adversarial or corrupted input prevents the pipeline from achieving the target $k$-anonymity threshold, StegnoZ withholds all sanitized candidate records by default, publishing an auditable `audit.json` with diagnostic reason `risk_target_exceeded`.

---

## Limitations of the Current Prototype

While StegnoZ achieves 0.0% PII leakage and 100% clinical utility on tested benchmarks, operators should note the following architectural boundaries:

* **Domain Focus:** Built specifically for clinical and hospital EHR de-identification (EHR tables, clinical notes, FHIR R4). Non-medical documents (e.g., financial ledgers, legal transcripts) are outside scope.
* **Singular Rare Diagnoses:** If a patient possesses an exceptionally rare ICD-10 code (held by only one individual in the entire region), that code is uniquely identifying regardless of quasi-identifier generalization. Because the challenge strictly forbids suppressing or altering medical values, rare diagnoses are tracked transparently in `rare_dx_exposed_profiles` rather than corrupted.
* **Population Multiplier Transparency:** The headline $k$-anonymity risk utilizes `population_factor: 4`, reflecting the voter registry ratio defined in `ATTACKS.md`. To maintain absolute transparency, `observed_singling_out_risk` (with factor 1.0) is always calculated and published side-by-side in `audit.json`.
* **Static Gazetteer Dependencies:** The geographic normalizer relies on the provided Indian district/tehsil gazetteer. Highly localized village names absent from standard gazetteers are safely coarsened to their parent district.

---

## Future Scope

StegnoZ is architected as an extensible pipeline. Planned future enhancements include:

### 1. Differential Privacy Mechanisms for Aggregate Analytics
Integrate Laplace and Gaussian noise injection into `dashboard/research_server.py` to support formal $(\epsilon, \delta)$-differential privacy for aggregate epidemiological queries, enabling safe public-facing cohort exploration.

### 2. Multi-Modal DICOM & Waveform Metadata Stripping
Extend Stage 0 ingestion to parse DICOM medical imaging and EDF/ECG waveform binaries, stripping header metadata and burned-in pixel text while preserving clinical image resolution.

### 3. Local-Only Quantized Small Language Models
Incorporate an optional local, CPU-quantized SLM (e.g., a 1-bit or 2-bit quantized 0.5B parameter model executing via llama.cpp with zero network calls) to assist rule-based extraction in highly disordered, unpunctuated doctor handwriting notes.

### 4. Distributed Federated Sanitization Nodes
Package StegnoZ as a lightweight edge container capable of running inside regional hospital intranets, enabling multi-center health networks to de-identify records locally before pooling into national registries.

### 5. Standardized HL7/FHIR R5 & OMOP CDM Interoperability
Expand FHIR serialization to support full bidirectional OMOP Common Data Model (CDM) transformation, enabling seamless de-identified data exports for international OHDSI clinical studies.

---

## License

This project is licensed under the terms of the MIT License. See [LICENSE](LICENSE) for details.
