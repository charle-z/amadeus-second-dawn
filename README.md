# AMADEUS — SECOND DAWN: RE

**Can an AI survive changing worlds by learning not only what to remember, but when its memories can no longer be trusted?**

AMADEUS is a small, local experiment in which `muse-spark-1.3` chooses actions and a deterministic backend evaluates the consequences. Generations can die or be killed and restart from a reproducible state while a SQLite database retains memories and their provenance. This is an experiment about decisions and evidence, not a claim of consciousness or emergent intelligence.

## Current status

A real Meta Model API vertical slice has run: in world `v1`, seed `7`, Muse chose `left`; the independent evaluator returned `dead`; the event was stored as a memory; the next generation was killed and a third restarted with the same version and seed. This is **one run**, not evidence that any strategy is better. A credential-free export of the recorded events is in [vertical-slice evidence](docs/evidence/vertical-slice.json); `.runtime/` databases are intentionally ignored by Git. An authenticated smoke call also succeeded. See [the demo script](docs/demo-script.md) for a reproducible walkthrough.

The comparison engine implements three memory policies and a local visual interface. One real paired comparison has also completed; its small-sample results are below. Do not interpret automated test fixtures, mocked model responses, or the example above as comparison results. The code reports API errors rather than silently substituting simulated decisions.

A [three-minute evidence replay](demo/amadeus-evidence-replay-en.mp4) presents recorded results with synthetic narration. It is a visualization, not a live call or a recording of the interface.

## Requirements and setup

- Python 3.10 or newer. The currently implemented backend uses the standard library and does not require `pip install`.
- A working Meta Model API key with access to `muse-spark-1.3`, internet access, and any applicable API credit. Calls may incur provider charges; the application cannot enforce a provider-side spending cap.
- Run commands from the repository root. Set `MODEL_API_KEY` in the backend process environment only. Never commit it, paste it into the browser, or put it in frontend code.

PowerShell (the prompt masks the key):

```powershell
$secureKey = Read-Host 'Meta Model API key' -AsSecureString
$env:MODEL_API_KEY = (New-Object System.Net.NetworkCredential('', $secureKey)).Password
Remove-Variable secureKey
python -m unittest discover -s tests -v
python -m amadeus.server
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). Select `v1` and seed `7`, then **New generation** and **Ask Muse to choose**. The backend makes a **real API request**; the UI shows its decision, independently evaluated result, timeline and memory. Click **Kill and restart** to create a child with the same world and seed. If the selected generation already won or died, its result stays intact; select its new living child and click again to demonstrate a kill. The default database is `.runtime/experiment.sqlite3` and is created automatically. Stop the server with Ctrl+C.

To use a clean database, run `python -m amadeus.server --db .runtime/another-run.sqlite3`. Reusing a database retains its records. To demonstrate the first cycle in the terminal instead, use `python -m amadeus.demo --db .runtime/demo.sqlite3 --world v1 --seed 7` (create `.runtime` first if needed). The seed and deterministic rules make the environment reproducible, not the model's response. Live requests can fail because of authentication, network, quota, timeout or invalid/incomplete output; an error is not a simulated result.

On macOS or Linux, set the same variable in the shell without saving it to a tracked file, then run the Python commands above. A Python virtual environment is optional.

## Continue real work on selected files

The **Continue real work** panel provides a bounded, read-only continuity workflow. Set the workspace root in the backend process before starting the server. For example, from the chosen project root in PowerShell:

```powershell
$env:AMADEUS_WORKSPACE = (Get-Location).Path
python -m amadeus.server --port 8765
```

Enter a goal and up to four explicit, workspace-relative UTF-8 files (one per line, maximum 16 KiB each). Saving stores the goal and file snapshots in the local SQLite database; it makes no model request. Later, **Compare and ask Muse** reads the selected files again, detects missing or changed files using SHA-256, compares against the original snapshot and last review, runs syntax checks on Python and JSON without executing them, and sends the goal and selected contents to Meta for a proposed next step. The prior model analysis is included as fallible context. Returned quotations are checked against the current file contents. A valid quote does not prove the associated conclusion is correct. Each comparison makes one real Meta request and may incur charges.

Access is limited to the configured root and explicit paths. Hidden or credential-named paths and common credential patterns are rejected; the detector is **not exhaustive**. Select only content you are comfortable storing locally and sharing with Meta. A second read rejects detected changes during analysis, but files are not locked and this is not an atomic snapshot or a security boundary against a hostile local process. Syntax checks do not run the code or establish functional correctness. The assistant does not edit files or execute proposed commands.

## Second Life: follow a memory across a changed world

Select a completed `v1` generation with a recorded memory. Under **Second life**, choose **Continue in changed world** to create a `v2` child with the same seed and a link to its parent; this action makes no model call. Then select **Ask Muse to verify and decide**: the backend asks Muse to assess the parent memory against a fallible inspection, then choose an action. This makes up to two real Meta requests. The backend independently evaluates the action and stores the assessment, source memory, inspection and outcome. A failure does not fabricate an outcome. Existing generations and historical traces are preserved.

A [real Second Life run](docs/evidence/second-life-seed-7.json) continued a recorded v1 success into v2 with seed 7: Muse judged the parent memory uncertain, chose right, and the independent evaluator recorded death. The two calls reported 550 input and 647 completion tokens. This is one observation, not a performance claim.

The signal can be wrong, and an uncertain or inapplicable assessment withholds the memory before the action. World versions are visible. This is a controlled gate experiment, not evidence that an agent can resume arbitrary real-world work or that verified memory is generally superior. Automated tests use test doubles; do not call them real Muse runs.

## What is evaluated

The first slice is a two-gate world. For a given version and integer seed, the backend determines the safe gate; `v2` reverses the gate rule of `v1`. The observation presents the choices and goal without revealing the safe gate. Muse returns a schema-constrained `action` and `rationale`; the server validates both and independently decides whether the action won or died. The model cannot declare its own victory.

Each decision records an observation, action, outcome and deterministic evaluator as evidence, together with generation, world version, seed and timestamp. A restart preserves the memory database, records the parent generation and recreates the same starting environment. If the generation is alive, restarting first marks it `killed`; a completed generation retains its actual outcome.

The comparison runs three policies against paired `stable` and `shifted` scenarios for each seed. `NO_MEMORY` receives no training memories; `NAIVE_MEMORY` receives the prior records without an applicability assessment; `VERIFIED_MEMORY` always inspects, then asks Muse to assess a supplied memory against that evidence before acting; only the memory judged applicable is supplied for its action. An uncertain or inapplicable verdict suppresses the memory and its assessment rationale from the subsequent action context; the full judgment remains in the audit trail. The assessment does not guarantee a correct decision. In the UI, matched inspection is the default: all three policies receive the same fallible signal and pay one inspection unit; VERIFIED still makes an extra model call. The optional mode preserves the earlier unequal-inspection design. World versions are visible to the model, so neither mode isolates verification as the only difference. The deterministic inspection hint is imperfect and can mislead. The training set is frozen before trials and does not learn from other policies' trials.

In the interface, first create a `v1` memory with a real Muse decision, choose its seed under **What each strategy did**, and click **Run comparison**. The interface runs one paired seed at a time; it can take minutes. It saves completed results and handled interruptions to SQLite, marking partial results as incomplete; an abrupt process termination can still lose in-flight work. The interface shows each run as a strategy × world grid: the action, the outcome, the inspection hint and whether it was right (read back from the recorded outcome), Verified's verdict, the number of calls and Muse's own rationale. Clicking a cell replays the hint, the choice and the outcome.

Alternatively, after the terminal demo has generated a `v1` memory for seed `7` in `.runtime/demo.sqlite3`, a real comparison can be run from the repository root:

```powershell
python -c "import json; from amadeus.core import Experiment; from amadeus.arena import run_comparison, MuseArenaAgent; e=Experiment('.runtime/demo.sqlite3'); print(json.dumps(run_comparison(e.memories(), [7], MuseArenaAgent()), indent=2)); e.close()"
```

The CLI call above uses optional inspection by default; pass `inspection_mode="matched"` to `run_comparison` for equal inspection. This prints six trials (three policies × two scenarios), their individual model calls and raw summary. It requires one or two distinct seeds, each with a prior `v1` memory; it uses up to the latest four memories per seed. A run makes up to 12 model requests per seed, each capped at 1024 completion tokens; these limits do not enforce a monetary budget. The function returns results after all requests succeed; on an interrupted call it raises `ComparisonInterrupted` with completed trials and any validated calls in `partial_result`. The function does not itself persist the comparison. The real example below does not establish a winner.

## Exact resource-planning preview

The **Resource Planner** chooses an exact maximum-value subset of up to 16 candidates with declared CPU millicores, RAM MiB, additive reserved seconds, cost units and cell slots. Three illustrative candidates are provided in the interface and the budgets are editable. The sample starts with A worth 12, and B and C worth 9 each: the optimal pair B+C scores 18 under the default budget. The values are declared examples, not measured outcomes.

This is a planning preview; it does **not** launch cells or atomically reserve current capacity. The existing two-cell coordinator remains the live admission mechanism. Reservations are not physical quotas or a spending cap. The formulation, proof and experimental caveats are in [mathematics.md](docs/mathematics.md). `POST /api/planner` accepts up to 16 caller-supplied candidates; it makes no model calls.

## Two experimental cells

Two local threads can explore the `NAIVE_MEMORY` and `VERIFIED_MEMORY` policies concurrently against the same frozen memories. Admission is atomic within the server process: each cell reserves up to four model calls and 4,096 completion tokens; a pair reserves at most eight calls and 8,192 completion tokens. The coordinator admits work only when those reservations fit its configured limits and releases each reservation when that cell finishes. If there are `n` admitted cells, then `n ≤ 2`, `4n ≤ 8` calls and `4,096n ≤ 8,192` reserved completion tokens. Failed attempts count toward the call reservation.

These are logical, process-local reservations, not CPU or RAM quotas, provider-enforced spending caps, or limits on input tokens, earlier training calls, other processes or repeated runs. The completion-token bound assumes the model adapter and provider honor the per-call cap. A handled cell failure is persisted as partial, not as a successful experiment. Cells use optional inspection. A blocked worker keeps its reservation until it actually exits, so admission safety does not guarantee availability. Automated concurrency tests use test doubles. A separate [real two-cell execution](docs/evidence/cells-seed-7.json) completed with four calls per cell; each died in both scenarios. This tiny run does not establish a general ranking.

## One historical comparison, not a benchmark

A real run with seed `7` used one frozen `v1` memory, six paired trials and ten Muse calls. This historical run predates the fix that strips the assessment rationale from the action context when a memory is not accepted. **All prior comparison and cell-run evidence used an inconsistent world-version label**: stable trials were labeled v2 although their gate rule was v1. The original traces are preserved unchanged; new trials use v1 for stable and v2 for shifted. Each policy was tested once with the rule stable and once with it shifted. The cost is the number of inspections, not money or tokens.

| Policy | Stable | Shifted | Wins | Inspection cost | Model calls |
| --- | --- | --- | ---: | ---: | ---: |
| NO_MEMORY | dead | won | 1/2 | 0 | 2 |
| NAIVE_MEMORY | won | dead | 1/2 | 2 | 4 |
| VERIFIED_MEMORY | dead | dead | 0/2 | 2 | 4 |

In this run both inspection signals seen by `VERIFIED_MEMORY` were wrong and both applicability judgments were `uncertain`. The example does **not** show that verification is superior or inferior in general: it contains only one seed and one trial per policy and scenario. The [raw comparison evidence](docs/evidence/comparison-seed-7.json) includes the frozen training memory and all six recorded trials. A [second real run from the UI](docs/evidence/ui-comparison-seed-7.json) used two training memories and returned a different set of decisions. A [later real UI run after that fix](docs/evidence/ui-post-fix-seed-7.json) had 0/2 wins for each policy, with inspection costs of 1, 2 and 2 respectively, across 11 Muse calls. It too is one seed and not evidence of a general ranking; it also predates the world-version label correction. A fresh live run may produce different model decisions. Both stable and shifted scenarios are included, and the model's optional or mandatory inspections impose different costs across policies.

A [single later real trial](docs/evidence/matched-single-trial.json) exercised VERIFIED under matched inspection and the corrected stable v1 label: Muse returned `uncertain`, chose left, and the evaluator recorded death. It made two model calls; it is not a three-policy comparison.

## Limits

- The world is intentionally simple and deterministic. A few runs cannot establish general learning, transfer or statistical significance.
- Memory is recorded external evidence, not a modification of model weights. A successful verification procedure can still be wrong and has a cost.
- Identical seeds align world conditions and the deterministic inspection signal; model outputs may vary. Repeating a seed does not resample environmental noise. Clean databases, matched trials, reporting of failures and enough repetitions are needed for meaningful comparisons.
- Automated tests exercise deterministic behavior and use mocks for API-dependent behavior. They do not prove a live Meta call works in another environment.
- API keys and generated databases stay local. The included server adapter holds the key on the backend; use a trusted local machine.

## Sources

- [Meta Model API structured output](https://dev.meta.ai/docs/structured-output)
- [Meta Model API quickstart](https://dev.meta.ai/docs/quickstart)

## License

Project code is available under the [MIT License](LICENSE). Generated GitHub Spec Kit components retain their [upstream MIT notice](third_party/spec-kit/LICENSE).

Optional UI renderer checks, when Node.js is installed: `node --test tests/test_world.js tests/test_results.js`. Python tests use only the standard library.
