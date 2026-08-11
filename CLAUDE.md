# VLA-for-GUI

## What this is

A local vision-language agent that completes tasks on real GUIs (browser-based apps) by looping screenshot → plan → detect → ground → act → verify. The core research claim: UI element detection + set-of-marks prompting + a small VLM fine-tuned on app-specific grounding data beats raw VLM coordinate prediction, measured by a rigorous eval harness comparing base vs. fine-tuned models with ablations. Phase 1 is fully open source, fully local, no paid APIs.

This is a portfolio/research artifact for AI engineering interviews, not a shipped product — reproducibility and documented reasoning matter as much as the agent working. See `PRD.md` for the full spec and `tasks.md` for the build breakdown.

## Status

**Phase 4 done.** Next up: dispatch the Phase 5 batch (T-5.1–T-5.3) in `tasks.md`.

**Confirmed model-capability limit, not a pipeline bug (2026-08-11):** the base `qwen3-vl:2b-instruct` planner does not reliably track multi-step task state. `verify/rules.py`'s success condition is correct (returns `"success"` when the right 2-step sequence is actually executed — confirmed directly). `orchestrate.py`'s step-history string is under-informative (`"click -> uncertain"`, no record of *what* was clicked — a real, separate, non-blocking issue, tracked as [[T-4.5]]).

The precise finding, from a channel-isolated diagnostic (visual state and textual history varied independently, not combined as in the first pass): given a screenshot with the checkbox visibly checked and the label struck through, but **no history text at all**, the planner still re-planned "click the checkbox" — it does not use visual evidence of task progress on its own. Given the *original* (still-unchecked) screenshot but a history entry explicitly stating `"-> success, item is now marked complete"`, the planner correctly advanced to "click delete" — trusting text it was told over an image that contradicted it. The earlier (non-isolated) test that also failed to advance had used the word `"uncertain"` in its history (the verifier's real, correct output for a partial step) rather than `"success"` — suggesting the planner is keying off the literal success/uncertain lexical marker rather than reasoning over either the image or the description. **Net characterization for Phase 8: this is a visual state-tracking gap specifically — the model can locate elements from an image (Phase 3's ScreenSpot numbers) but does not use an image to infer *task progress*, and instead pattern-matches on literal result words in text history.** Phase 5's task suite should assume the base model reliably completes single-step actions, not multi-step sequences — size the ~20 tasks and their step budgets accordingly, and expect `step_budget_exceeded`/`uncertain` outcomes on anything beyond trivial tasks until Phase 7's fine-tuning targets this specific gap.

## Roadmap

- [x] **Phase 0 — Skeleton + contracts.** uv project, config, step-log schema, coordinate-transform module, ablation protocols.
- [x] **Phase 1 — Targets + executor + oracle.** 4 self-hosted Docker apps up and resettable; Playwright executor with pinned viewport; DOM/a11y oracle for ground truth.
- [x] **Phase 2 — Detector + set-of-marks.** OmniParser (GPU icon-detect / CPU captioner split) and OpenCV fallback behind one interface; numbered-box renderer.
- [x] **Phase 3 — Grounder + first real number.** `qwen3-vl:2b-instruct` via Ollama, SoM + raw-coordinate modes; component-level grounding eval on ScreenSpot (hit-rate primary).
- [x] **Phase 4 — Planner + verifier + orchestrator.** Structured single-action planner; rule-based verifier (VLM verifier as ablation); LangGraph loop with checkpointing and step budget.
- [ ] **Phase 4 — Planner + verifier + orchestrator.** Structured single-action planner; rule-based verifier (VLM verifier as ablation); LangGraph loop with checkpointing and step budget.
- [ ] **Phase 5 — Task suite + eval harness + API.** ~20 tasks across the 4 apps; CLI eval harness with base/fine-tuned + ablation comparison; FastAPI service for the demo.
- [ ] **Phase 6 — Dataset.** Oracle auto-labels at scale; OmniParser labels + manual correction; merge with public training corpus; holdout split by page.
- [ ] **Phase 7 — Fine-tune + serve + compare.** Unsloth QLoRA on Colab T4 (ViT frozen, LoRA on LLM only); export to GGUF with stock mmproj; re-run eval on both models.
- [ ] **Phase 8 — Report, demo, reproducibility.** README with architecture and decision rationale, before/after results, failure modes; demo GIF; fresh-clone reproduction pass.

## Commands

```
uv sync                          # install deps
uv run vlagui run <task.yaml>    # run the agent loop on one task
uv run vlagui eval --model base,ft --ablate all --report out.md
uv run vlagui label              # dataset labeling workflow
uv run pytest                    # tests, colocated with source
docker compose up                # bring up the 4 target apps
ollama list                      # confirm qwen3-vl:2b-instruct (and later, the fine-tuned model) are present
```

Grounder model is `qwen3-vl:2b-instruct`, not `qwen3-vl:2b` — the unsuffixed tag maps to Ollama's thinking-variant renderer/parser, which returns an empty `response` on non-trivial prompts because it spends its whole token budget on hidden `<think>` reasoning first. `ollama pull qwen3-vl:2b-instruct` on a fresh machine.

## Layout

```
src/vlagui/
  config.py        # model names, viewport, step budget, paths
  schema.py        # StepRecord / RunRecord — the structured step log
  coords.py        # every image<->screen<->model-space coordinate transform
  protocols.py      # Detector / Grounder / Verifier interfaces (ablation seams only)
  browser.py        # Playwright executor: screenshot, click, type, scroll, reset
  oracle.py          # DOM/a11y ground truth — eval & labeling ONLY, never in the agent loop
  detect/            # omniparser.py, opencv.py
  som.py             # numbered set-of-marks renderer
  ground.py          # grounder: SoM element-ID mode + raw-coordinate mode
  plan.py             # planner: one structured action per step
  verify/             # rules.py (primary), vlm.py (ablation arm)
  orchestrate.py       # LangGraph loop: plan -> detect -> ground -> act -> verify
  eval/                # grounding.py, screenspot.py, harness.py
  data/                 # autolabel.py, correct.py, build.py
  api.py                 # FastAPI service
tasks/                    # per-task YAML: instruction, reset fixture, assertion, optimal steps
notebooks/                 # finetune.ipynb (Colab)
scripts/                    # export_gguf.sh
reports/                     # eval output
```

## Hard constraints

- **4 GB VRAM.** Only one VLM resident on GPU at a time. OmniParser's Florence-2 captioner never runs on GPU — CPU-only, offline, labeling time only. The icon-detect (YOLO) half is the only detector component allowed on GPU at agent runtime.
- **Ollama runs native on Windows**, not inside WSL2 — avoids GPU passthrough complexity. Docker Desktop still hosts the 4 target apps.
- **Viewport is pinned, `deviceScaleFactor=1`**, at the executor level, so screenshot pixels equal CSS pixels for every task.
- **`torch`/`torchvision` are pinned to a CUDA-13.1-matched index** (`pyproject.toml`'s `[tool.uv.sources]` / `[[tool.uv.index]]`, pointing at `download.pytorch.org/whl/cu130`) because PyPI's default Windows wheel is CPU-only and silently skips the GPU. A fresh clone on a different driver/CUDA version may need that index bumped to match — check `nvidia-smi`'s reported CUDA version first.

## Invariants that break the project if violated

- All coordinate math goes through `coords.py`. No inline pixel arithmetic anywhere else.
- Every agent step appends a `StepRecord` via `schema.py`. Nothing writes ad hoc logs.
- `oracle.py` is imported only from `eval/` and `data/`. If it is ever imported from `plan.py`, `ground.py`, or `orchestrate.py`, the pure-vision grounding claim is invalidated — the agent must never see the DOM.
- ScreenSpot is a clean held-out benchmark. It is never included in fine-tuning data, in `data/build.py` or anywhere else.
- Dataset holdout splits are by app/page, never a random sample — a random split leaks near-duplicate screenshots and inflates the reported fine-tuning gain.
- Grounder calls (`ground.py`) always pin `temperature=0`, overriding the Ollama Modelfile default of `1`. Confirmed by direct measurement: identical inputs at `temperature=1` produced different ScreenSpot hit-rates across runs (0.333 vs 0.4). Phase 5's ablation harness and Phase 7's base-vs-fine-tuned comparison depend on runs differing only in the thing being ablated — sampling noise must not be a hidden confound.

## Conventions

- `uv` for everything — never bare `pip install`.
- Pydantic models at every boundary (task specs, step logs, eval configs).
- Tests live next to the source file they cover (`ground.py` / `test_ground.py`), pytest, no fixture frameworks beyond what pytest gives for free.
- Structured logging (the step log itself, plus stdlib `logging`), no bare `print`.
