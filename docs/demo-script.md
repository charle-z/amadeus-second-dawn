# Three-minute demo script

This is a recording guide, not evidence that a new experiment has run. Use actual displayed results; if the API fails, say so. The visual interface and comparison are implemented. One real comparison is documented below; distinguish that previous run from anything newly recorded. Do not present mock test responses as live Muse decisions.

## Before recording

1. Set `MODEL_API_KEY` in the backend environment as shown in [README](../README.md), without showing the key on screen. Confirm access and network.
2. From the repository root, create `.runtime` if needed and run `python -m unittest discover -s tests -v`. Show a passing result only if it actually passes.
3. Start `python -m amadeus.server --db .runtime/video-run.sqlite3` and open `http://127.0.0.1:8765`. Use a fresh database path if you want a clean run. A clean run uses the same world conditions but may give a different model decision.
4. Before recording, make a V1 memory and complete a comparison in the UI; this makes several real calls and can take minutes. Completed runs and handled interruptions are saved, with partial runs marked incomplete; an abrupt process termination can still lose in-flight work. If it fails, use the pending wording below. Keep any evidence you want to preserve. API usage may incur charges.

## 0:00–0:25 — Question

> “What happens when an AI carries memories into a world whose rules have changed? AMADEUS tests whether an agent can decide when an old memory still applies. This is a controlled experiment, not a claim that the agent is conscious.”

Show the project title and experimental question.

## 0:25–1:15 — A real decision and independent consequence

In the interface, select V1 and seed 7, click **New generation**, then **Ask Muse to choose**. Show the actual action and resulting `won` or `dead` status in the timeline.

> “Muse chooses a gate. The backend owns the rules and checks the outcome independently; the model cannot award itself a win. A seed fixes the world, not the model's answer.”

If the run fails, show the error and stop claiming a live result. If it wins, say it won; do not describe it as a death.

## 1:15–1:45 — Memory and restart

Point to the recorded memory fields: generation, world version, seed, action, outcome and evidence. Click **Kill and restart**. If the selected generation has already ended, the new child starts alive; click **Kill and restart** again to show an actual kill and its child with the same world, seed and parent link.

> “The evidence survives across generations. Restarting a living generation kills it first; the next generation begins in the same reproducible environment. A previous result remains recorded as it happened.”

For the earlier real run on this machine, `.runtime/muse-slice-evidence.sqlite3` records `v1`, seed `7`, left, dead, then a killed generation and a new alive generation. This local, ignored database is not bundled with the public repository and is one observation only.

## 1:45–2:30 — Compare strategies

Use a previously completed live comparison to show `NO_MEMORY`, `NAIVE_MEMORY`, and `VERIFIED_MEMORY` in both stable and shifted conditions. Show the verification evidence and cost, and the raw result including failures. Explain that verification is fallible; it must not be an oracle. Report the real trial counts, not a predicted winner. If the new UI comparison fails, you can describe the earlier local evidence instead, without implying it is the new run: seed 7, six trials, ten real calls; NO_MEMORY 1/2 wins and zero inspections, NAIVE_MEMORY 1/2 and two inspections, VERIFIED_MEMORY 0/2 and two inspections. Both verified judgments were uncertain and both inspection hints were wrong. This older run predates the assessment-filtering correction; its raw record is `docs/evidence/comparison-seed-7.json`. A later corrected-code run is `docs/evidence/ui-post-fix-seed-7.json`: each policy won 0/2, with inspection costs of 1, 2 and 2, respectively. These six trials cannot establish a general winner.

## 2:30–3:00 — Interpretation and limitations

> “This is a small controlled world. Memory is external evidence, not training or consciousness. The backend keeps the outcomes auditable, and changing rules let us test when trusting old evidence helps or hurts. A single demonstration is not proof of general capability; meaningful conclusions require matched repeated trials and transparent failures.”

Show the repository and README, and state the actual implementation and results available at recording time.


## Optional Second Life walkthrough

In the local interface, select a completed v1 generation with an actual recorded memory, then choose **Continue in changed world**. This creates a v2 child linked to that parent with the same seed and makes no model call. Only when ready for real Meta API use, choose **Ask Muse to verify and decide**; it can make two real calls and may fail. Show the inspection, model verdict, actual choice and backend-evaluated outcome. If interrupted, show the partial evidence as incomplete. Do not claim the old video contains this feature or present a test-double trace as a live result.
