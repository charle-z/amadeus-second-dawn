# Planner and experiment limitations

The exact planner optimizes its declared additive-value, nonnegative-resource contract. It is a planning preview, not live admission or enforcement; logical reservations do not constrain physical CPU, RAM, provider spending, or total execution time. See [mathematics.md](mathematics.md) for the formulation and proof.

Handled comparison and cell failures retain partial evidence with an incomplete status; abrupt process termination can still lose in-flight work. Usage is recorded only when returned by the provider, and unknown usage is distinct from zero.

Matched inspection equalizes the signal and inspection cost, but VERIFIED_MEMORY makes an additional model call and world versions are visible. An uncertain verdict excludes a memory even if it might be correct, and the inspection signal can be wrong. Small samples do not support a general ranking of strategies.
