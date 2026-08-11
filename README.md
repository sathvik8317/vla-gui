# VLA-for-GUI

A local vision-language agent that completes tasks on real GUIs by looping screenshot, plan, detect, ground, act, verify. It runs entirely on a consumer GPU, against self-hosted target apps, with no paid APIs.

## Why this exists

Point a general-purpose vision-language model at a screenshot and ask it to click the right button, and it works fine on a simple demo and falls apart the moment the page has more than a handful of elements on it. Asking it for an exact pixel coordinate is the wrong ask: it will confidently return a point that is close, not on the button. Wiring that up to a real browser and letting it click blind is how you end up filing bug reports against your own agent instead of the app it's supposed to be testing.

The instinct most people reach for next is a bigger hosted model. That does not fix the underlying problem, it just makes each wrong click cost more. This project starts from the opposite assumption: grounding gets more reliable when you stop asking the model to guess coordinates freehand, and instead give it a shortlist.

**Core approach: UI element detection plus set-of-marks prompting plus a small VLM fine-tuned on app-specific grounding data beats raw VLM coordinate prediction.**

A detector proposes candidate UI element boxes on the screenshot first, a set-of-marks renderer numbers them, and the grounder picks a box ID instead of guessing raw coordinates. Phase 7 will fine-tune a small local VLM on hand-corrected, app-specific grounding data and compare it against the base model on the same held-out benchmark, to see how much of the remaining gap that closes.

Reproducibility and documented reasoning matter here as much as the agent working. Every phase in this repository's history records what was tried, what the numbers were, and what was learned, including the failure modes.

## Architecture

The agent loop, one line per component:

- **Executor** (`browser.py`): Playwright wrapper with a pinned viewport and `deviceScaleFactor=1`, so screenshot pixels equal CSS pixels; provides click, type, scroll, and reset.
- **Detector** (`detect/omniparser.py`, `detect/opencv.py`): proposes candidate UI element boxes on a screenshot; OmniParser (YOLO icon-detect on GPU, Florence-2 captioner CPU-only) is primary, OpenCV contour/template matching is the ablation arm.
- **Set-of-marks renderer** (`som.py`): draws numbered boxes over the screenshot so the grounder can select an element ID instead of a raw coordinate.
- **Grounder** (`ground.py`): a VLM (`qwen3-vl:2b-instruct` via Ollama) that maps an instruction to a specific box ID (set-of-marks mode) or a raw `(x, y)` coordinate (ablation mode).
- **Planner** (`plan.py`): decides the next single structured action (click, type, or scroll) given the task, the screenshot, and step history.
- **Verifier** (`verify/rules.py`, `verify/vlm.py`): judges each step success, failure, or uncertain; the rule-based verifier (DOM delta plus perceptual hash plus task assertion) is primary, a VLM-based verifier is the ablation arm.
- **Orchestrator** (`orchestrate.py`): a LangGraph state machine that wires plan to detect to ground to act to verify, with a step budget and a checkpointed, structured run log. This is the only module that imports all of the above; it never imports the DOM/a11y oracle, so the agent stays pure-vision at runtime.
- **Oracle** (`oracle.py`): DOM/a11y ground truth, used only for evaluation and dataset labeling, never by the agent loop itself.

## Current status

**Phase 4 is done. Phase 5 is in progress** (task suite written, eval harness and API not yet built). See `tasks.md` for the full roadmap and per-task board.

Completed so far:

- Skeleton, config, structured step-log schema, and coordinate-transform module (Phase 0).
- Four self-hosted Docker target apps (TodoMVC, Gitea, Juice Shop, Grafana) with a Playwright executor and a DOM/a11y oracle for ground truth (Phase 1).
- UI element detector (OmniParser and an OpenCV fallback) and a set-of-marks renderer (Phase 2).
- A grounder on `qwen3-vl:2b-instruct` with both set-of-marks and raw-coordinate modes, and a component-level grounding eval against ScreenSpot (Phase 3).
- A structured single-action planner, a rule-based verifier, and a LangGraph orchestrator loop with checkpointing and a step budget (Phase 4).
- Twenty task specs across the four target apps, biased toward short (one to two step) tasks (Phase 5, T-5.1).

Not done yet: there is no fine-tuned model, no eval harness or comparison report, no API, and no dataset. Any numbers below Phase 3 in the roadmap do not exist yet. The only measured number so far is the Phase 3 grounding hit-rate on ScreenSpot; there is no fine-tuned model to compare it against.

**A confirmed finding from Phase 4's diagnostic work, not a bug**: the base `qwen3-vl:2b-instruct` planner reliably completes single-step actions but does not reliably track multi-step task state. A controlled test isolating visual state from textual history showed the planner ignores unambiguous visual evidence of progress (a checked checkbox with struck-through text) but advances correctly when told in text that a step succeeded, and appears to key off literal result words in history rather than reasoning over either channel. This is a genuine capability limit of the base model, not a pipeline defect, and Phase 5's task suite was sized accordingly.

## Hardware constraint

This project targets **4 GB of VRAM** deliberately, not apologetically. Only one VLM is ever resident on GPU at a time. OmniParser's Florence-2 captioner runs CPU-only, offline, at labeling time only; the YOLO icon-detect half is the only detector component allowed on GPU at agent runtime. The point of the constraint is to prove the pipeline's grounding approach (detection plus set-of-marks plus targeted fine-tuning) can close the gap against raw VLM coordinate prediction without relying on a larger model or a paid API to do the work instead.

Ollama runs native on Windows, not inside WSL2, to avoid GPU passthrough complexity. Docker Desktop hosts the four target apps.

## How to run it

Requirements: `uv`, Docker Desktop, Ollama running natively on Windows with `qwen3-vl:2b-instruct` pulled, and (for GPU detection) a CUDA-capable card matching the pinned `torch`/`torchvision` index in `pyproject.toml`.

```
uv sync                          # install dependencies
docker compose up                # bring up the 4 target apps
ollama pull qwen3-vl:2b-instruct # not the unsuffixed "qwen3-vl:2b" tag, see note below
ollama list                      # confirm the model is present

uv run vlagui run <task.yaml>    # run the agent loop on one task
uv run vlagui eval --model base,ft --ablate all --report out.md   # not built yet (Phase 5, T-5.2)
uv run pytest                    # run the test suite
```

Use `qwen3-vl:2b-instruct`, not `qwen3-vl:2b`. The unsuffixed tag maps to Ollama's thinking-variant renderer and parser, which spends its whole token budget on hidden reasoning and returns an empty response on non-trivial prompts.

A fresh clone on a different GPU driver or CUDA version may need `pyproject.toml`'s pinned PyTorch index bumped to match; check `nvidia-smi`'s reported CUDA version first, since PyPI's default Windows wheel is CPU-only and will silently skip the GPU.

## Known issues

One real, open bug, tracked so it does not get lost before Phase 8's failure-mode writeup:

- **Orchestrator step history loses the click target (T-4.5).** `_verify_node`'s history entries are built as `f"{action.type} -> {result}"` (for example `"click -> uncertain"`), which drops what was actually clicked. This is a real gap in what the planner can see across steps, though a controlled diagnostic confirmed it is not the cause of Phase 4's stuck-loop behavior on multi-step tasks (see the status note above). Deferred to Phase 8's failure-mode section rather than fixed speculatively.

Fixed since Phase 5 started: `type` actions previously never pressed Enter, which structurally blocked `todomvc-03` and `todomvc-05`. `Action`/`PlannedStep` now carry a `submit` flag, and `_act_node` presses Enter after typing when the planner sets it. Unconditionally pressing Enter after every `type` was considered and rejected: `grafana-05` types a username then a password before clicking Log in, and an early Enter would submit the form with the password field still empty, changing the task's actual outcome. Whether `todomvc-03`/`05` pass end to end now depends on the small planner actually choosing `submit=True` for a single-field form, which is a separate, already-documented reliability question, not a structural block.

## Layout

```
src/vlagui/
  config.py, schema.py, coords.py, protocols.py   # shared contracts
  browser.py, oracle.py                            # executor and DOM ground truth
  detect/, som.py                                   # detector and set-of-marks renderer
  ground.py                                          # grounder
  plan.py                                            # planner
  verify/                                            # rule-based (primary) and VLM (ablation) verifiers
  orchestrate.py                                     # LangGraph agent loop
  eval/                                               # grounding eval, ScreenSpot harness
tasks/                                                 # per-task YAML specs
targets/                                               # self-hosted target app configs
docker-compose.yml                                     # the 4 target apps
```

See `tasks.md` for the full roadmap and per-task dependency board.
