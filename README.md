# AMADEUS — SECOND DAWN: RE

**Can an AI survive changing worlds by learning not only what to remember, but when its memories can no longer be trusted?**

AMADEUS is a small, local experiment in which `muse-spark-1.3` chooses actions and a deterministic backend evaluates the consequences. Generations can die or be killed and restart from a reproducible state while a SQLite database retains memories and their provenance. This is an experiment about decisions and evidence, not a claim of consciousness or emergent intelligence.

## Current status

A real Meta Model API vertical slice has run: in world `v1`, seed `7`, Muse chose `left`; the independent evaluator returned `dead`; the event was stored as a memory; the next generation was killed and a third restarted with the same version and seed. This is **one run**, not evidence that any strategy is better. A credential-free export of the recorded events is in [vertical-slice evidence](docs/evidence/vertical-slice.json); `.runtime/` databases are intentionally ignored by Git. An authenticated smoke call also succeeded. See [the demo script](docs/demo-script.md) for a reproducible walkthrough.

The comparison engine implements three memory policies and a local visual interface. One real paired comparison has also completed; its small-sample results are below. Do not interpret automated test fixtures, mocked model responses, or the example above as comparison results. The code reports API errors rather than silently substituting simulated decisions.

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

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). Select `V1` and seed `7`, then **Start generation** and **Run Muse decision**. The backend makes a **real API request**; the UI shows its decision, independently evaluated result, timeline and memory. Click **Kill & restart** to create a child with the same world and seed. If the selected generation already won or died, its result stays intact; select its new living child and click again to demonstrate a kill. The default database is `.runtime/experiment.sqlite3` and is created automatically. Stop the server with Ctrl+C.

To use a clean database, run `python -m amadeus.server --db .runtime/another-run.sqlite3`. Reusing a database retains its records. To demonstrate the first cycle in the terminal instead, use `python -m amadeus.demo --db .runtime/demo.sqlite3 --world v1 --seed 7` (create `.runtime` first if needed). The seed and deterministic rules make the environment reproducible, not the model's response. Live requests can fail because of authentication, network, quota, timeout or invalid/incomplete output; an error is not a simulated result.

On macOS or Linux, set the same variable in the shell without saving it to a tracked file, then run the Python commands above. A Python virtual environment is optional.

## What is evaluated

The first slice is a two-gate world. For a given version and integer seed, the backend determines the safe gate; `v2` reverses the gate rule of `v1`. The observation presents the choices and goal without revealing the safe gate. Muse returns a schema-constrained `action` and `rationale`; the server validates both and independently decides whether the action won or died. The model cannot declare its own victory.

Each decision records an observation, action, outcome and deterministic evaluator as evidence, together with generation, world version, seed and timestamp. A restart preserves the memory database, records the parent generation and recreates the same starting environment. If the generation is alive, restarting first marks it `killed`; a completed generation retains its actual outcome.

The comparison runs three policies against paired `stable` and `shifted` scenarios for each seed. `NO_MEMORY` receives no training memories; `NAIVE_MEMORY` receives the prior records without an applicability assessment; `VERIFIED_MEMORY` always inspects, then asks Muse to assess a supplied memory against that evidence before acting; only the memory judged applicable is supplied for its action. An uncertain or inapplicable verdict suppresses the memory and its assessment rationale from the subsequent action context; the full judgment remains in the audit trail. The assessment does not guarantee a correct decision. The other two policies may also inspect once, optionally, for the same cost of one unit. The deterministic inspection hint is imperfect and can mislead. The training set is frozen before trials and does not learn from other policies' trials.

In the interface, first create a `v1` memory with a real Muse decision, choose its seed in **Compare strategies**, and run the comparison. The interface runs one paired seed at a time; it can take minutes. It saves results to SQLite only after all calls complete. The interface shows each strategy's action, outcome, cost, decision, inspection and evidence.

Alternatively, after the terminal demo has generated a `v1` memory for seed `7` in `.runtime/demo.sqlite3`, a real comparison can be run from the repository root:

```powershell
python -c "import json; from amadeus.core import Experiment; from amadeus.arena import run_comparison, MuseArenaAgent; e=Experiment('.runtime/demo.sqlite3'); print(json.dumps(run_comparison(e.memories(), [7], MuseArenaAgent()), indent=2)); e.close()"
```

This prints six trials (three policies × two scenarios), their individual model calls and raw summary. It requires one or two distinct seeds, each with a prior `v1` memory; it uses up to the latest four memories per seed. A run makes up to 12 model requests per seed, each capped at 1024 completion tokens; these limits do not enforce a monetary budget. The function returns results only after all requests succeed; it does not itself persist the comparison. The real example below does not establish a winner.

## Two experimental cells

Two local threads can explore the `NAIVE_MEMORY` and `VERIFIED_MEMORY` policies concurrently against the same frozen memories. Admission is atomic within the server process: each cell reserves up to four model calls and 4,096 completion tokens; a pair reserves at most eight calls and 8,192 completion tokens. The coordinator admits work only when those reservations fit its configured limits and releases each reservation when that cell finishes. If there are `n` admitted cells, then `n ≤ 2`, `4n ≤ 8` calls and `4,096n ≤ 8,192` reserved completion tokens. Failed attempts count toward the call reservation.

These are logical, process-local reservations, not CPU or RAM quotas, provider-enforced spending caps, or limits on input tokens, earlier training calls, other processes or repeated runs. The completion-token bound assumes the model adapter and provider honor the per-call cap. A failed cell is reported as partial, not as a successful experiment. A blocked worker keeps its reservation until it actually exits, so admission safety does not guarantee availability. Automated concurrency tests use test doubles. A separate [real two-cell execution](docs/evidence/cells-seed-7.json) completed with four calls per cell; each died in both scenarios. This tiny run does not establish a general ranking.

## One historical comparison, not a benchmark

A real run with seed `7` used one frozen `v1` memory, six paired trials and ten Muse calls. This historical run predates the fix that strips the assessment rationale from the action context when a memory is not accepted. Each policy was tested once with the rule stable and once with it shifted. The cost is the number of inspections, not money or tokens.

| Policy | Stable | Shifted | Wins | Inspection cost | Model calls |
| --- | --- | --- | ---: | ---: | ---: |
| NO_MEMORY | dead | won | 1/2 | 0 | 2 |
| NAIVE_MEMORY | won | dead | 1/2 | 2 | 4 |
| VERIFIED_MEMORY | dead | dead | 0/2 | 2 | 4 |

In this run both inspection signals seen by `VERIFIED_MEMORY` were wrong and both applicability judgments were `uncertain`. The example does **not** show that verification is superior or inferior in general: it contains only one seed and one trial per policy and scenario. The [raw comparison evidence](docs/evidence/comparison-seed-7.json) includes the frozen training memory and all six recorded trials. A [second real run from the UI](docs/evidence/ui-comparison-seed-7.json) used two training memories and returned a different set of decisions. A [later real UI run after that fix](docs/evidence/ui-post-fix-seed-7.json) had 0/2 wins for each policy, with inspection costs of 1, 2 and 2 respectively, across 11 Muse calls. It too is one seed and not evidence of a general ranking. A fresh live run may produce different model decisions. Both stable and shifted scenarios are included, and the model's optional or mandatory inspections impose different costs across policies.

## Limits

- The world is intentionally simple and deterministic. A few runs cannot establish general learning, transfer or statistical significance.
- Memory is recorded external evidence, not a modification of model weights. A successful verification procedure can still be wrong and has a cost.
- Identical seeds align world conditions; model outputs may vary. Clean databases, matched trials, reporting of failures and enough repetitions are needed for meaningful comparisons.
- Automated tests exercise deterministic behavior and use mocks for API-dependent behavior. They do not prove a live Meta call works in another environment.
- API keys and generated databases stay local. The included server adapter holds the key on the backend; use a trusted local machine.

## Sources

- [Meta Model API structured output](https://dev.meta.ai/docs/structured-output)
- [Meta Model API quickstart](https://dev.meta.ai/docs/quickstart)

## License

Project code is available under the [MIT License](LICENSE). Generated GitHub Spec Kit components retain their [upstream MIT notice](third_party/spec-kit/LICENSE).
