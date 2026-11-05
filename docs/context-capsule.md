# Context capsule

## Purpose

AMADEUS combines a read-only continuity assistant for explicitly selected workspace files with a controlled experiment on the applicability of memory across changing rules.

## Continuity workflow

The configured workspace bounds file access. A saved objective, selected snapshots and optional progress notes survive process restarts. Local checks compare files and run non-executing Python and JSON syntax checks without a model call; they report whether files or saved notes changed since the last model review. Model reviews include the saved notes and ask Muse for an assessment with literal source quotations. The interface shows recent reviews. Deleting an objective removes its associated local snapshots, notes and reviews.

Selected files and objectives are stored locally and sent to Meta when a model review is requested. Credential filtering is not exhaustive. File reads are not atomic snapshots against hostile concurrent writers; model recommendations require human review and are not executed automatically.

## Controlled experiment

World rules and outcomes are independently evaluated by the backend. Memory records contain their source and outcome. NO_MEMORY, NAIVE_MEMORY and VERIFIED_MEMORY can be compared with matched but fallible inspection. The model assesses applicability; a verified verdict does not guarantee a correct action. Evidence and known limitations are documented in the README and docs/evidence/.

Cell admission uses process-local logical reservations. The exact planner is a separate preview; neither mechanism enforces operating-system CPU or memory quotas or provider spending limits.

## Verification

Run the automated Python and JavaScript suites described in the README. Model tests use test doubles unless an artifact explicitly records a real provider call. Keep credentials outside the repository and do not modify unrelated projects.
