# Context capsule

## Goal
Ship a reproducible demonstration of memory applicability in deterministic changing worlds using real Muse decisions.

## Current state
2026-11-04: repository was empty. Authenticated `muse-spark-1.3` response succeeded with minimal reasoning (12 input and 17 output tokens); an earlier 256-token attempt ended incomplete. The first real vertical slice, three-policy comparison, and local interface are implemented and tested. Real traces are in docs/evidence/; the repo is public. Two concurrent cells passed an independent admission review and completed a real run; reservations do not enforce CPU/RAM or spending quotas. A bounded exact selection preview and matched-inspection mode were added after an independent GPT-6 Astra xhigh review. A single new matched trial was verified with two Muse calls.

## Decisions and risks
- Small local monolith, deterministic server evaluator, validated model decisions.
- No fabricated results or concealed fallbacks; changing and stable rules must both be tested.
- Store MODEL_API_KEY outside the repository; request budgets limit calls/tokens but are not provider-side spend caps.
- Existing similar work includes EvoArena/EvoMem and GAMBIT; the project is an auditable demonstration, not a novelty claim.
- GitHub is public and the experiment and planning changes were published through Step 09. Historical comparisons used inconsistent world-version labels; their evidence remains unchanged.

## Next
Verify and publish the current revision, record or use the labeled replay, and complete the event submission before 9 p.m. Colombia; the event form requires the user to sign in. No claim of general superiority: both recorded comparisons have tiny samples.


## Pro review and interruption evidence — 2026-11-04

ChatGPT interface reasoning level Pro 5/5 reviewed public commit `4ab0602e999ae73249fbc244a852785f79cd3028`. See [pro-review.md](pro-review.md) for its scope and limits. Subsequent code preserves handled partial comparisons and cell runs as incomplete; an abrupt process termination can still lose in-flight evidence. No new Muse calls were made for the review or regression tests.


## Second Life — 2026-11-04

A v1 generation with a recorded outcome can create a v2 child with the same seed. An explicitly requested verified step uses only the parent memory, a fallible inspection and at most two model calls. The backend independently determines the outcome, persists provenance, and records handled interruptions without inventing outcomes. Automated tests use test doubles. A subsequent real two-call Muse trace is preserved in docs/evidence/second-life-seed-7.json: verdict uncertain, action right, outcome dead; 550 input and 647 completion tokens. This one observation establishes no general ranking. The existing video predates it and is labeled a historical evidence replay.


## Practical continuity — 2026-11-04

A separate read-only workflow stores a user objective and snapshots of explicitly selected files within AMADEUS_WORKSPACE, compares actual changes on resume, checks Python/JSON syntax without execution, and asks Muse to reconsider the prior analysis with validated quotations. It requires a configured workspace and an explicit click before sending selected content to Meta. Secret filters are not comprehensive; no file execution, editing or atomic filesystem snapshot is claimed.

One real practical review used two public project files and detected a real specification change; Muse returned three literally verified citations and a next step. One request reported 1,513 input / 449 completion tokens. Its proposed test may already be covered elsewhere; the model saw only selected files. Evidence: docs/evidence/work-continuity-real.json.

A user-confirmed deletion removes one selected local work objective, its snapshots and analysis from the configured workspace database; it does not erase backups, published evidence or information already sent to Meta.

Completed work reviews are stored as separate records; the interface shows up to five. The previous last-result-only format is migrated without inventing a timestamp. Deleting a work objective removes its associated review records locally.
