# Personal AI-SDLC Constitution

This is the small layer that should travel across projects. Keep it short.

## Non-Negotiables

1. Design before implementation for non-trivial projects.
2. Tests before code for every implementation step.
3. Architecture must be proportional to the problem.
4. Prefer existing mature tools over building meta-frameworks.
5. Security, secrets, deployment, and maintenance are first-class concerns.
6. Never let chat history be the only source of truth.
7. Keep context capsules current enough for future AI sessions.
8. Do not over-document obvious code; document decisions and interfaces.
9. Do not add dependencies or services without a reason.
10. Every step must be verifiable.

## Architecture Proportionality

Default to the simplest architecture that preserves testability and future change.

Escalate only when needed:

- from script to modules when behavior grows;
- from modules to layered architecture when boundaries matter;
- from layered to hexagonal when adapters are volatile;
- from simple domain model to DDD when domain rules are complex;
- from monolith to services only when operational independence is worth the cost.

## AI Agent Rules

- Read before editing.
- Search before assuming.
- Write tests first.
- Keep changes small.
- Run verification.
- Do not revert user changes.
- Update context capsule when project state changes.

## Token Discipline

- Short prompts.
- Durable docs.
- Current context capsule.
- Explicit file list for each task.
- Avoid pasting entire chat histories.

## Build Bias

Prefer shipping a small verified slice over polishing methodology indefinitely.
