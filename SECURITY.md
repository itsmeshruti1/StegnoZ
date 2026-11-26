# Storage and release security

StegnoZ processes synthetic organizer data. Its input is read-only; neither a privacy failure nor a crash authorizes changing the original dataset.

## Implemented boundary

- The pipeline never persists raw copies or decoded intermediate records. These exist in process memory.
- Every verified candidate written during policy search uses AES-256-GCM authenticated encryption. A fresh 256-bit key is generated in memory for each Pipeline instance; a monotonically increasing 96-bit nonce prevents reuse within that instance. The file's internal staging name is authenticated as associated data. File substitution, wrong keys and ciphertext changes fail authentication.
- The candidate key is not derived from or stored beside RAKSHA_SECRET. Losing the process loses that key. Normal completion and handled exceptions remove temporary candidate files.
- Only a selected release is decrypted into the private publication directory. The default CLI withholds records when the proxy target fails. `--allow-risk-miss` explicitly permits publication despite failure and is enabled in the competition entry point.
- Pseudonyms and date offsets use separate HMAC-derived keys. Logs contain stage names, counts and exception types. Reports identify input files by SHA-256. No raw record values or secret keys are intentionally logged.

## Required deployment controls

Encryption of organizer-owned raw input and final published output is a storage responsibility: mount an encrypted filesystem (for example LUKS on Linux or BitLocker on Windows), keep its unlock credentials separate from the dataset, and restrict access to the service account. StegnoZ cannot retroactively encrypt a read-only input volume. This repository does not claim that the user's disk has encryption enabled.

Keep the output volume encrypted too: an authorized release is ordinary UTF-8 CSV/JSON/FHIR/text as required by the contract, and the final publication directory can contain that plaintext before the report is committed. Encrypt or disable swap and core dumps, and restrict debugging/process access. Python does not guarantee erasure of all in-memory key or plaintext copies.

After an unhandled process termination, encrypted candidate remnants may remain, and an authorized publication may be incomplete. Inspect the coarse completion report before consuming a release. The CLI requires a new empty output directory and does not silently overwrite a partial previous run.

## Verified and unverified claims

Regression tests check encryption, nonce freshness, tamper/file-substitution rejection, wrong-key rejection, default withholding, and cleanup after normal processing. Organizer practice checks assess identifiers and canaries. Neither those checks nor the internal observed-class proxy prove anonymity against all auxiliary knowledge. Hidden attacks and deployment volume encryption must be assessed separately.
