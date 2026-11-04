# Context capsule

## Goal
Ship a reproducible demonstration of memory applicability in deterministic changing worlds using real Muse decisions.

## Current state
2026-11-04: repository was empty. Authenticated `muse-spark-1.3` response succeeded with minimal reasoning (12 input and 17 output tokens); an earlier 256-token attempt ended incomplete. The first real vertical slice, three-policy comparison, and local interface are implemented and tested. Real traces are in docs/evidence/; the repo is public. Two concurrent cells passed an independent admission review and completed a real run; reservations do not enforce CPU/RAM or spending quotas.

## Decisions and risks
- Small local monolith, deterministic server evaluator, validated model decisions.
- No fabricated results or concealed fallbacks; changing and stable rules must both be tested.
- Store MODEL_API_KEY outside the repository; request budgets limit calls/tokens but are not provider-side spend caps.
- Existing similar work includes EvoArena/EvoMem and GAMBIT; the project is an auditable demonstration, not a novelty claim.
- GitHub repo is initially empty and public. Network and local Git credentials need verification for publication.

## Next
Record the demo, verify the final repository, inspect submission requirements, and submit before the deadline. No claim of general superiority: both recorded comparisons have tiny samples.
