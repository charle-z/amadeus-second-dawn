# Implementation boundaries

- Keep the backend responsible for deterministic world rules and independent outcome evaluation.
- Persist attributed memories, generations and experiment evidence, including incomplete runs where possible.
- Compare memory policies using reproducible worlds and disclose differences in information, calls and inspection cost.
- Keep resource planning separate from process-local admission and do not represent reservations as operating-system quotas.
- Support bounded, read-only continuity for explicitly selected workspace files, with deterministic checks and independently validated model citations.
- Protect credentials, disclose transmission of selected files, and validate changes with automated tests.
