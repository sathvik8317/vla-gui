# VLA-for-GUI — Task Board

A dispatch board for sub-agents, organized along the component seams (planner, detector, grounder, verifier, executor, orchestrator, eval, dataset, finetune, docs). Batches map 1:1 onto the phases in `CLAUDE.md`'s roadmap.

## How to use this

1. Claim a task by ID. Check its `depends-on` — do not start until every dependency is `done`.
2. Read its **files owned** line and build only those files. Tasks within the same phase batch own disjoint files by design — this is what makes them safe to run in parallel.
3. For Phase 3 onward, read the batch's **sub-agent brief** before starting — you are cold and need that context.
4. Run the task's **check**. If it fails, the task is not done.
5. Update the `status` column: `todo` → `in_progress` → `done`.

Global contracts every task codes against (do not redefine): `schema.py` (T-0.2), `coords.py` (T-0.3), `protocols.py` (T-0.4). Protocols exist **only** where FR-18's ablation requirement demands real multiplicity — `Detector` (OmniParser | OpenCV), `Grounder` (base | fine-tuned), `Verifier` (rules | VLM). Planner and executor are one implementation each — plain modules, no interface.

---

## Phase 0 — Skeleton + contracts *(sequential — blocks everything downstream)*

| ID | Status | Depends | Files owned | Deliverable |
|---|---|---|---|---|
| T-0.1 | done | — | `pyproject.toml`, `src/vlagui/__init__.py`, `config.py` | uv project scaffold; model names, viewport, step budget, paths as config |
| T-0.2 | done | T-0.1 | `schema.py` | `StepRecord` / `RunRecord` Pydantic models, JSONL round-trip |
| T-0.3 | done | T-0.1 | `coords.py` | Every image↔screen↔model-space transform, one tested place |
| T-0.4 | done | T-0.2 | `protocols.py` | `Detector`, `Grounder`, `Verifier` protocol definitions only |

**Check:** `RunRecord` round-trips through JSONL with equality; a coordinate transform composed with its inverse is identity.

---

## Phase 1 — Targets + executor + oracle

| ID | Status | Depends | Files owned | Deliverable |
|---|---|---|---|---|
| T-1.1 | done | T-0.1 | `docker-compose.yml`, `targets/README.md` | TodoMVC, Gitea, Juice Shop, Grafana up; documented reset-to-known-state per app |
| T-1.2 | done | T-1.1, T-0.3 | `browser.py` | Playwright wrapper: pinned viewport, DPR=1, screenshot, click/type/scroll at real coordinates, `reset()` |
| T-1.3 | done | T-1.2 | `oracle.py` | DOM/a11y tree → labeled ground-truth boxes. Eval + labeling only |

**Check:** click a known button via oracle-resolved coordinates, assert the expected DOM state change; all 4 targets reset cleanly.

---

## Phase 2 — Detector + set-of-marks

| ID | Status | Depends | Files owned | Deliverable |
|---|---|---|---|---|
| T-2.1 | done | T-0.4 | `detect/omniparser.py` | Icon-detect (YOLO) on GPU; Florence-2 captioner CPU-only, offline |
| T-2.2 | done | T-0.4 | `detect/opencv.py` | Contour/template fallback, also the ablation arm for "no OmniParser" |
| T-2.3 | done | T-0.4 | `som.py` | Numbered set-of-marks renderer over a screenshot |

**Check:** both detectors return boxes on a fixture screenshot; SoM render produces a valid image with N visibly numbered labels.

---

## Phase 3 — Grounder + first real number

**Sub-agent brief:** Phases 0–2 are done. You have `protocols.py::Grounder`, `som.py` (numbered-box images), and `schema.py`. `ground.py` calls the *already-running* Ollama model `qwen3-vl:2b` (confirmed present via `ollama list`) — do not re-pull or reconfigure Ollama. This is the first component with a measurable number attached; treat the eval script as equally important as the grounder itself, not an afterthought.

| ID | Status | Depends | Files owned | Deliverable |
|---|---|---|---|---|
| T-3.1 | done | T-0.4, T-2.3 | `ground.py` | `qwen3-vl:2b-instruct` grounder: SoM element-ID selection mode + raw `(x,y)` fallback mode |
| T-3.2 | done | T-0.4 | `eval/grounding.py`, `eval/screenspot.py` | Component-level eval on ScreenSpot (clean, never trained on) + DOM-oracle local set. **Hit-rate is primary**, median normalized distance secondary |

**Check:** `eval/grounding.py` runs end to end and emits a metrics JSON with a hit-rate number.

---

## Phase 4 — Planner + verifier + orchestrator

**Sub-agent brief:** Phases 0–3 are done: you have a working grounder with a baseline hit-rate. Now build the loop around it. `plan.py` and `verify/rules.py` are independent of each other — build them in parallel. `orchestrate.py` is a LangGraph `StateGraph` that wires plan → detect → ground → act (via `browser.py`) → verify, and is the *only* place that should import all of the above; it must never import `oracle.py` (agent must stay pure-vision). Every step it runs must produce one `StepRecord`.

| ID | Status | Depends | Files owned | Deliverable |
|---|---|---|---|---|
| T-4.1 | done | T-0.2 | `plan.py` | Planner: one schema-constrained action per step (`click`/`type`/`scroll` minimum) |
| T-4.2 | done | T-0.4, T-1.3 | `verify/rules.py` | Rule-based verifier: DOM delta + perceptual hash + task assertion |
| T-4.3 | done | T-0.4 | `verify/vlm.py` | VLM-based verifier, ablation arm only |
| T-4.4 | done | T-4.1, T-4.2, T-3.1 | `orchestrate.py` | LangGraph loop, checkpointer, step budget, graceful termination with logged reason |
| T-4.5 | deferred (known issue) | T-4.4 | `orchestrate.py` | `_verify_node`'s history entries are `f"{action.type} -> {result}"` (e.g. `"click -> uncertain"`) — losing the resolved target/description, so the planner can't see *what* it already clicked. Real bug, but diagnostically confirmed NOT the cause of the Phase 4 check's stuck-loop behavior (a controlled test with rich, explicit history — including the word "success" — still failed under ambiguous conditions; see CLAUDE.md status for the full diagnosis). Deferred so it's tracked for Phase 8's failure-mode section rather than lost in prose. |

**Check:** full loop completes one trivial two-step task against a self-hosted target and writes a well-formed run log (`RunRecord` + `StepRecord`s validate against `schema.py`).

**Note on T-4.2's dependency on T-1.3:** `verify/rules.py` does *not* import `oracle.py` — it takes `dom_before`/`dom_after` as plain strings that the caller (`orchestrate.py`) captures itself via `browser.py`'s `Page.content()`. This keeps `oracle.py` unreachable from `orchestrate.py`'s import graph (confirmed by grep + `sys.modules` check), while still giving the verifier real DOM-delta signal. The T-1.3 dependency arrow reflects conceptual lineage (DOM ground truth), not an actual import.

---

## Phase 5 — Task suite + eval harness + API

**Sub-agent brief:** The agent loop (`orchestrate.py`) works end to end on at least one task. Now scale that to the full suite and wrap it in a CLI. `tasks/*.yaml` must be written before `eval/harness.py` can be tested against more than one task — write task specs first even if built in parallel with the harness code. The harness's job is exactly what FR-16/17/18 demand: one command in, a full comparison report out, nothing hand-collated.

| ID | Status | Depends | Files owned | Deliverable |
|---|---|---|---|---|
| T-5.1 | done | T-1.1 | `tasks/*.yaml` | 20 tasks, 5 per app; each declares seed actions, success assertion, optimal step count up front. Distribution revised to 12×1-step / 5×2-step / 3×3-step (was "capped 3–6") — biased toward short tasks per the confirmed planner sequencing limit (see CLAUDE.md status); a 3–6-step-heavy suite would mostly measure that limit, not grounding accuracy |
| T-5.2 | done | T-4.4, T-5.1 | `eval/harness.py`, `cli.py` | `vlagui eval --model base\|ft --ablate no-som,no-detector,vlm-verifier --report out.md`. Completion rate + steps-to-completion per FR-16; click accuracy is intentionally NOT computed here (see note below) |
| T-5.3 | done | T-4.4 | `api.py` | FastAPI `POST /run`, `GET /runs/{id}`, SSE step stream — powers the Phase 8 demo |

**Check:** one CLI invocation produces a complete comparison/ablation report with zero manual result collation. Verified: a live 2-task run (`gitea-01`, `grafana-01`) against the real stack produced a correctly formatted `reports/eval_report.md` with a summary table and per-task detail, no manual collation.

**Notes on T-5.3's implementation:**
- `orchestrate.py`'s `Orchestrator.run()` used LangGraph's `.invoke()`, which only returns the final state after the whole run completes — nothing to stream per step. Added `run_streaming()`, using LangGraph's own `.stream(stream_mode="updates")` (already available via the installed `langgraph` dependency) rather than inventing bespoke per-node instrumentation; it yields each `StepRecord` as the `verify` node produces it, then a final `{outcome, termination_reason}` dict. `run()` itself is untouched behaviorally; only the initial-state setup was factored into a shared `_initial_state()` helper.
- A run is driven from a plain daemon `threading.Thread`, not `async def` handlers: `browser.py`/`ground.py`/`plan.py` are all synchronous (Playwright sync API, blocking Ollama HTTP calls), so making the API async would mean rewriting the whole agent loop, not just the API layer. `POST /run` starts the thread and returns the run_id immediately (202); `GET /runs/{id}` and the SSE stream both read from the same in-memory state the thread updates.
- Verified live end to end, not just written: started the server, ran `grafana-01` via `POST /run`, watched both real `StepRecord`s and the final outcome arrive over the SSE stream in order, confirmed `GET /runs/{id}` reflected the completed run afterward, and confirmed 404s for an unknown `run_id` and an unknown `task_id`.
- Added `vlagui serve` to `cli.py` (`uvicorn.run("vlagui.api:app", ...)`) so the API is reachable through the same CLI as `run`/`eval`, not a separate uvicorn invocation the README would have to explain on its own.

**Notes on T-5.2's implementation:**
- Fixed a structural blocker found while starting this task: `orchestrate.py`'s `_act_node` never called `Executor.press("Enter")` after typing, which blocked `todomvc-03`/`05`. Added a `submit` flag to `Action`/`PlannedStep` rather than always pressing Enter, since always pressing it would break `grafana-05` (typing a username must not submit before the password field is filled).
- `orchestrate.py`'s `Orchestrator` had no way to swap in the OpenCV detector, raw-coordinate grounder, or VLM verifier — `protocols.py`'s ablation seams existed but were never wired to anything. Added `detect_fn`/`ground_fn`/`verify_fn` constructor params (defaulting to the Phase 2-4 primary implementations) so `eval/harness.py`'s `--ablate` flag has something real to swap. This touches a Phase 4-owned file from a Phase 5 task; noted here since it crosses the file-ownership lines the phase table otherwise keeps disjoint.
- Click accuracy (also part of FR-16) isn't computed by the harness. Considered and rejected: having `eval/harness.py` call `oracle.get_ground_truth_boxes(page)` live at each grounding decision during a task run (same isolation pattern as `eval/grounding.py` — orchestrate.py still never imports oracle.py, only harness.py would). The blocker isn't the plumbing, it's that there's no reliable way to turn a task's natural-language instruction into "the one correct oracle box" automatically. Confirmed live on two supposedly clean, single-step cases: juice-shop's welcome-banner close button has no accessible label at all (7 elements on that page return `label=""` — icon-only buttons, nothing to string-match "its close button" against), and todomvc's new-todo input is labeled `"What needs to be done?"` (its placeholder), which has no textual overlap with the instruction's "the input field" — it only resolves because there happens to be exactly one interactive element on the page. A robust version needs either per-step ground-truth target labels authored by hand for all 20 tasks (real content work — and multi-step tasks would still need someone to decide what "correct" means at each intermediate step, since only the final task_assertion is declared today), or an NL-to-label matching heuristic whose own error rate is unverified, which would be exactly the kind of hidden confound the temperature-pinning and ScreenSpot-isolation invariants exist to avoid. See the FR coverage index: click accuracy stays at T-3.2 (component-level, ScreenSpot + local oracle, where each example is genuinely an (instruction, target box) pair by construction), completion rate and steps-to-completion stay at T-5.2 (task-level). This is a documented split, not a gap expected to close later in this project.
- Confirmed live: `gitea-01` hit a one-off Playwright `Page.screenshot` CDP protocol error (3/3 retries succeeded in isolation) — a transient infra flake, not a harness or orchestrator bug. `orchestrate.py`'s blanket exception handler in `run()` already converts this into `outcome="failure"` with 0 steps, which is indistinguishable from a genuine failure in the report unless `termination_reason` is shown, so the per-task table now includes it.

---

## Phase 6 — Dataset

**Sub-agent brief:** The eval harness (Phase 5) works but has only run the base model so far — no fine-tuned model exists yet. This phase builds the training data. `oracle.py` (Phase 1) gives exact, free ground truth on the 4 target apps — use it for scale. OmniParser's captioner (Phase 2, CPU path) gives candidate labels on top of that for the vision-only subset, which then need a manual correction pass. The critical rule: **holdout is split by app/page, never by random sample** — random splitting leaks near-duplicate screenshots between train and test and inflates the fine-tuning result this whole project exists to report.

| ID | Status | Depends | Files owned | Deliverable |
|---|---|---|---|---|
| T-6.1 | todo | T-1.3 | `data/autolabel.py` | Oracle auto-labels at scale across the 4 targets |
| T-6.2 | todo | T-2.1 | `data/correct.py` | OmniParser candidate labels + manual correction workflow |
| T-6.3 | todo | T-6.1, T-6.2 | `data/build.py` | Merge with public training corpus (SeeClick/OS-Atlas/WaveUI, decided here — not ScreenSpot); holdout split by page |

**Check:** dataset-stats script asserts zero page overlap between the train split and the holdout split.

---

## Phase 7 — Fine-tune + serve + compare

**Sub-agent brief:** The dataset (Phase 6) is built and holdout-clean. Training happens on Colab (free T4), not locally — the 4 GB card is for inference only. The one constraint that must not be violated: **freeze the ViT and merger, LoRA the LLM only**. This is what lets the exported model pair with the stock `qwen3-vl` mmproj already in Ollama — if the vision tower gets touched, the export step breaks. After export, this phase reruns the *exact same* Phase 3 and Phase 5 eval code (not a rewrite) against the new model so the comparison is apples-to-apples.

| ID | Status | Depends | Files owned | Deliverable |
|---|---|---|---|---|
| T-7.1 | todo | T-6.3 | `notebooks/finetune.ipynb` | Unsloth QLoRA on Colab T4; ViT + merger frozen, LoRA on LLM only |
| T-7.2 | todo | T-7.1 | `scripts/export_gguf.sh`, `Modelfile` | Merge → GGUF → paired with stock `qwen3-vl` mmproj → `ollama create vlagui-grounder` |
| T-7.3 | todo | T-7.2, T-5.2 | `reports/` | Re-run T-3.2 grounding eval and T-5.2 task eval on both base and fine-tuned models |

**Check:** the fine-tuned model answers through Ollama; the comparison report has both the base and fine-tuned columns populated with real numbers.

---

## Phase 8 — Report, demo, reproducibility

**Sub-agent brief:** Everything upstream is built and has produced real numbers (Phase 7's `reports/`). This phase is synthesis and packaging only — no new pipeline code. Pull failure modes from the actual `StepRecord` logs already on disk, not from memory of how the project went.

| ID | Status | Depends | Files owned | Deliverable |
|---|---|---|---|---|
| T-8.1 | todo | T-7.3 | `README.md` | Architecture, decision rationale (why SoM, why this action space, why rule-based verifier, why 4 GB is a deliberate constraint), dataset methodology, before/after table, failure modes mined from logs |
| T-8.2 | todo | T-4.4 | `docs/demo.gif` | One full task completed end to end, recorded |
| T-8.3 | todo | T-8.1 | *(none — verification only)* | Fresh clone to a clean directory; follow only the README; confirm the eval numbers reproduce |

**Check:** the fresh-clone reproduction in T-8.3 reproduces the numbers in `README.md` without any undocumented manual step.

---

## FR coverage index

Every FR-1…FR-18 from `PRD.md` §6 traced to the task(s) that satisfy it:

| FR | Task(s) |
|---|---|
| FR-1 (accept task + starting URL/app) | T-4.4 |
| FR-2 (screenshot each step) | T-1.2 |
| FR-3 (one structured action per step) | T-4.1 |
| FR-4 (click/type/scroll action types) | T-4.1 |
| FR-5 (grounder: element ID or raw coords) | T-3.1 |
| FR-6 (executor: real input event) | T-1.2 |
| FR-7 (verifier: success/failure/uncertain) | T-4.2, T-4.3 |
| FR-8 (step budget, graceful termination) | T-4.4 |
| FR-9 (structured, replayable step log) | T-0.2, T-4.4 |
| FR-10 (detector: boxes + labels) | T-2.1, T-2.2 |
| FR-11 (numbered annotated screenshot / SoM) | T-2.3 |
| FR-12 (labeled dataset: public + hand-corrected) | T-6.1, T-6.2, T-6.3 |
| FR-13 (fine-tuning pipeline, versioned checkpoint) | T-7.1, T-7.2 |
| FR-14 (base + fine-tuned, same harness) | T-7.3 |
| FR-15 (fixed task suite, 3–5 apps, ~20 tasks) | T-5.1 |
| FR-16 (completion rate, click accuracy, steps-to-completion) | T-3.2 (click accuracy, component-level), T-5.2 (completion rate, steps-to-completion, task-level) — intentional split, see note below |
| FR-17 (base vs. fine-tuned comparison report) | T-5.2 |
| FR-18 (ablation flag) | T-5.2, T-0.4 |

Every row has at least one task ID — no FR is unassigned.

## File-ownership check

No two tasks within the same phase batch write to the same file — this is what makes each phase batch dispatchable as parallel sub-agents rather than sequential. Verified by inspection above; the only cross-phase file re-touch is `reports/` (T-7.3, written once) and `README.md` (T-8.1, written once) — neither is contended within its own batch.

## Carried-forward decisions

- Exact Docker image tags for the 4 targets — pinned in T-1.1 when pulled, not guessed here.
- Training corpus (SeeClick vs. OS-Atlas vs. WaveUI) — decided in T-6.3 on license + web-split size; blocks nothing before Phase 6.
