# Experimental planning and admission

## Exact selection (preview)

For each candidate `i`, the caller declares a non-negative integer value `v_i` and reservation vector `r_i = (CPU, RAM, time, cost)`. Every candidate occupies one cell. For budget vector `B` and cell limit `K`, the planner chooses a subset `S` maximizing `sum(v_i)` subject to `sum(r_i[j]) <= B[j]` for every resource and `|S| <= K`. It checks all feasible subsets of at most 16 candidates. The empty subset is included. Ties prefer fewer cells, then lexicographically ordered IDs.

All resources are non-negative, so rejecting a partial subset that already exceeds any capacity cannot discard a feasible superset. Every feasible subset is otherwise visited; the best feasible value seen when the search ends is therefore optimal **for this declared additive objective**. Worst case is `2^n` subsets, bounded here by `2^16 = 65,536`. Estimates are not measured outcomes and interactions between candidates are outside this objective. The estimate for one candidate need not be independent of another for linearity of expectation, but the objective must actually be additive.

For example, with CPU budget 10 and two slots, candidates A=(CPU 6, value 12), B=(CPU 5, value 9), C=(CPU 5, value 9) give greedy A a value of 12, while exact selection B+C gives 18. These values are illustrative, not experimental outcomes. If both actual cells fit and both have positive values, selecting both is already optimal; a planner does not create a benefit merely by existing.

### Estimated value and duplication

Suppose every estimate has a verified absolute error bound `|v_i - v_i_true| <= epsilon` and every feasible selection has at most `k` cells. Let `S_hat` maximize estimated value and `S_true` maximize true additive value over the same feasible sets. Then `V_true(S_true) - V_true(S_hat) <= 2*k*epsilon`: each selected sum differs from its estimate by at most `k*epsilon`, and the estimated optimum is at least the estimate of `S_true`. This is conditional mathematics, not a measured guarantee: the project has not established any such error bound.

More cells can be worse when value is not additive. For example, suppose two cells duplicate the same experiment: either alone produces information worth 10, together still produce information worth 10, and running the second incurs a cost of 1. Their combined net value is 9, less than running one. The additive selector cannot recognize that overlap unless the caller models it; its exact optimum is only as appropriate as its objective.

This selector is a **preview**, not the live admission gate. It uses declared CPU millicores, MiB, summed reserved seconds, arbitrary cost units and cell count. Sum of reserved seconds is not a parallel wall-clock makespan. Between preview and admission, capacity can change; the existing cell coordinator separately performs atomic process-local admission. Neither mechanism enforces physical CPU/RAM or account-wide spending. Optimality and reservations do not establish runtime performance or survival.

## Live cell reservations

The existing coordinator admits work under one lock, with at most two active cell leases. If `n` leases are active, `0 <= n <= 2`; each lease reserves 4 calls and `4 * MAX_COMPLETION_TOKENS` output tokens. Thus their sums never exceed 8 calls and `8 * MAX_COMPLETION_TOKENS` output tokens under the coordinator contract. Failed attempts count as calls. A worker retains its lease until it actually exits. A submission gate prevents a job enqueued before a failed thread submission from performing an unadmitted call.

These are guarantees about one shared in-process coordinator and the declared adapter cap, assuming synchronous workers and provider compliance. A stuck worker may retain its reservation indefinitely; other processes, input tokens, actual billing and physical resource usage are not controlled by this proof.

## Memory experiment

The matched-inspection option gives all three policies the same deterministic, fallible inspection for a given seed and scenario, at the same inspection cost. VERIFIED also makes an extra model call to assess applicability; the visible world version differs between stable and shifted scenarios. Thus the comparison still bundles memory handling, prompting and model-call overhead, and it is not a blind or isolated causal estimate of verification alone.

A seed fixes the world and the inspection signal. Repeating the same seed does not resample environmental noise. Muse decisions can vary; a handful of runs cannot establish a general improvement. Historical stored comparisons are retained without rewriting; earlier runs used a version label inconsistent with the core evaluator, corrected for new runs.
