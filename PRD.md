# Product Requirements Document

## Project: VLA-for-GUI — Vision-Language-Action Agent for GUI Automation (Phase 1)

---

## 1. Overview

This project builds an AI agent that completes tasks on a computer by looking at screenshots and taking actions, the same way a human would: read the screen, decide what to do, click or type, check the result, repeat until the task is done.

The core technical challenge is **visual grounding**: turning a natural-language instruction like "click the login button" into an exact pixel coordinate on the screen. General-purpose vision-language models (VLMs) are unreliable at this. This project builds a pipeline that improves grounding accuracy through UI element detection, set-of-marks prompting, and fine-tuning, and rigorously evaluates the result against ground truth.

Phase 1 is fully open source and runs locally. No paid APIs are used in this phase.

---

## 2. Goals

- Build a working multi-step GUI agent (planner → grounder → verifier) that completes real tasks on a small set of target apps/websites.
- Build a UI element detection preprocessing step that improves grounding accuracy over raw VLM coordinate prediction.
- Fine-tune a small local VLM on a hand-corrected grounding dataset specific to the target apps, and demonstrate measurable improvement over the base model.
- Build a rigorous evaluation harness with task-completion rate, click accuracy, and steps-to-completion metrics.
- Produce a reproducible, documented, portfolio-quality repository with a working demo.

### Non-goals (explicitly out of scope for Phase 1)

- No paid/hosted API integration (OpenAI, Anthropic, etc.) — this is Phase 2.
- No mobile app support — desktop and browser only.
- No multi-monitor or multi-window juggling — single window/tab focus per task.
- No natural-language task decomposition beyond simple, single-goal tasks (e.g. "log in and change the email" is fine; "reorganize my entire inbox by 12 different rules" is not).
- No production deployment, auth, or multi-user support. This is a research/portfolio project, not a shipped product.

---

## 3. Target Users

This is a solo portfolio/research project. The "user" of the final artifact is:
- The developer (Sathvik), demoing this in AI engineering job interviews.
- Anyone evaluating the GitHub repo as a signal of applied agentic AI, CV, and DL capability.

---

## 4. Core Concepts & Architecture

### 4.1 Agent Loop

```
[Task instruction] 
      ↓
[Screenshot capture]
      ↓
[Planner: decide next action] → e.g. "click the Submit button"
      ↓
[UI Element Detector: find candidate regions] → numbered boxes on screenshot
      ↓
[Grounder: map instruction to a specific box/coordinate]
      ↓
[Action Executor: perform click / type / scroll]
      ↓
[Screenshot capture]
      ↓
[Verifier: did the expected state change happen?]
      ↓
   [Loop until task complete, max steps reached, or verifier signals failure]
```

### 4.2 Components

| Component | Responsibility |
|---|---|
| **Planner** | Given the task, the current screenshot, and action history, decides the next single action in natural language. |
| **UI Element Detector** | Runs over the raw screenshot, detects and localizes UI elements (buttons, fields, links, icons), and annotates the screenshot with numbered bounding boxes (set-of-marks). |
| **Grounder** | Given the planner's instruction and the annotated screenshot, selects the correct numbered box (or, as a fallback, predicts raw pixel coordinates directly). |
| **Action Executor** | Translates the grounded coordinate/element into an actual mouse click, keyboard input, or scroll event. |
| **Verifier** | Given a before/after screenshot pair and the intended action, judges whether the action succeeded, failed, or had no effect. |
| **Orchestrator** | Manages the loop, state, retries, and step budget across the above components. |
| **Eval Harness** | Runs the agent against a fixed task suite and computes metrics. |
| **Fine-tuning Pipeline** | Prepares the labeled dataset and fine-tunes the grounding model. |

---

## 5. Tech Stack (Phase 1 — Open Source Only)

| Layer | Tool | Notes |
|---|---|---|
| Planning model | Qwen3-VL 2B (via Ollama) | Local inference, reused from existing local-first inference proxy setup. |
| Grounding model | Qwen3-VL 2B (via Ollama), fine-tuned | Same base model, fine-tuned separately for grounding accuracy. |
| UI element detection | OmniParser | Purpose-built open-source model for UI element detection and labeling. Fallback: OpenCV contour/template-based detector if OmniParser is too heavy for available VRAM. |
| Action execution (browser) | Playwright | Preferred for target apps that are web-based — easier to sandbox, reset state, and script deterministic test tasks. |
| Action execution (desktop) | PyAutoGUI | Used only if any target app is a native desktop app rather than a browser tab. |
| Orchestration | LangGraph | Reuses checkpointing/state-machine pattern from the existing LangGraph CLI agent project. |
| Fine-tuning | Unsloth + QLoRA | Same recipe as the DesiTutor fine-tuning project, applied to Qwen3-VL 2B. |
| Backend/service layer | FastAPI | Exposes the agent loop as a service, consistent with the existing document intelligence agent project's structure. |
| Dataset labeling workflow | OmniParser auto-labels + manual correction | See Section 7. Screenspot (public dataset) used for base fine-tuning volume. |
| Eval harness | Custom Python scripts | Pixel-distance-to-ground-truth, task-completion rate, steps-to-completion vs. optimal. |
| Environment | Python via `uv`, WSL2, RTX 3050 4GB VRAM | Existing hardware constraint; treated as a documented differentiator in the writeup, not hidden. |

---

## 6. Functional Requirements

### 6.1 Agent Capabilities
- FR-1: The agent must accept a natural-language task description and a starting URL/app as input.
- FR-2: The agent must capture a screenshot of the current state at each step.
- FR-3: The planner must produce exactly one next action per step, in a structured format (action type + target description).
- FR-4: Supported action types at minimum: `click`, `type`, `scroll`. (Additional types like `drag` or `hover` are optional stretch scope.)
- FR-5: The grounder must output either a selected element ID (from set-of-marks) or raw (x, y) pixel coordinates.
- FR-6: The action executor must translate the grounded output into a real input event on the target app/site.
- FR-7: The verifier must compare before/after screenshots and produce a success/failure/uncertain judgment for each action.
- FR-8: The orchestrator must enforce a maximum step budget per task and terminate gracefully (success, failure, or budget-exceeded) with a logged reason.
- FR-9: Every step (screenshot, planner output, grounder output, action taken, verifier judgment) must be logged in a structured, replayable format for later analysis and demo generation.

### 6.2 UI Element Detection
- FR-10: The detector must take a raw screenshot and output a list of bounding boxes with associated labels/types where possible.
- FR-11: The detector's output must be renderable as a numbered, annotated screenshot (set-of-marks) for use in grounder prompts.

### 6.3 Fine-tuning
- FR-12: A labeled dataset of (screenshot, instruction, ground-truth coordinate/box) triples must be constructed, combining a public dataset (Screenspot) with hand-corrected app-specific examples.
- FR-13: The fine-tuning pipeline must produce a versioned, reproducible fine-tuned model checkpoint.
- FR-14: The base model and fine-tuned model must both be evaluable through the same eval harness, so before/after comparison is possible.

### 6.4 Evaluation
- FR-15: The eval harness must run a fixed suite of tasks (target: 3-5 apps/sites, ~20 tasks total) end to end and record outcomes.
- FR-16: Metrics computed must include: task completion rate, click accuracy (pixel distance from predicted to ground-truth target), and steps-to-completion vs. an optimal/reference step count.
- FR-17: The eval harness must support running against both the base (non-fine-tuned) model and the fine-tuned model, and output a comparison report.
- FR-18: The eval harness must support an `--ablations` style flag or equivalent, so individual pipeline components (e.g. set-of-marks on/off) can be toggled and compared, consistent with the pattern used in the `mmsearch-eval` CLI.

---

## 7. Dataset Plan

1. **Base volume**: Use the public Screenspot dataset (or Screenspot-Pro if feasible) for general grounding fine-tuning volume.
2. **App-specific data**: Select 3-5 target apps/websites. Capture 20-30 screenshots per app.
3. **Auto-labeling**: Run OmniParser over these screenshots to generate candidate element boxes and labels.
4. **Manual correction**: Manually review and correct OmniParser's output (fix wrong boxes, add missed elements, correct labels). This produces a small, high-quality, app-specific labeled set.
5. **Combine**: Merge public dataset + corrected app-specific set for the fine-tuning run.
6. **Holdout**: Reserve a portion of the app-specific labeled data (not used in fine-tuning) purely for evaluation, so eval numbers reflect genuine generalization within the target apps, not memorization.

---

## 8. Evaluation Metrics (Detail)

| Metric | Definition |
|---|---|
| Task completion rate | % of tasks in the eval suite completed successfully within the step budget. |
| Click accuracy | Pixel (or normalized) distance between predicted coordinate and ground-truth target center, averaged across all grounding decisions. |
| Steps-to-completion | Number of agent steps taken vs. a manually-defined optimal step count for each task; reported as a ratio or delta. |
| Grounding accuracy (component-level) | Independent of full-task success — measures grounder correctness in isolation against the held-out labeled set. |
| Verifier accuracy | Measures whether the verifier's success/failure judgment matches actual ground-truth task state, on a sampled/spot-checked basis. |

Base model vs. fine-tuned model must be reported side by side on every metric above.

---

## 9. Deliverables

1. GitHub repository containing:
   - Full agent implementation (planner, grounder, verifier, orchestrator).
   - UI element detection integration.
   - Fine-tuning pipeline and scripts.
   - Eval harness with CLI, supporting base/fine-tuned comparison and ablations.
   - Structured logs from eval runs.
2. A written report (README or separate doc) covering:
   - Architecture overview.
   - Dataset construction methodology.
   - Before/after fine-tuning results.
   - Documented failure modes and the specific fixes applied (e.g. misclicks on visually similar elements, coordinate drift across resolutions, ambiguous instructions).
   - Hardware/constraint notes (4GB VRAM) framed as a deliberate efficiency constraint.
3. A demo video or GIF showing the agent completing at least one full task end to end on a real app/site.

---

## 10. Success Criteria

- The agent completes a majority of the ~20-task eval suite without human intervention.
- The fine-tuned grounding model shows a measurable, reported improvement in click accuracy over the base model on the held-out app-specific set.
- The eval harness runs end to end via a single CLI command and produces a comparison report (base vs. fine-tuned, and ablation on/off) without manual result-collation.
- All architectural decisions (why set-of-marks, why this action space, why this verifier design) are documented with reasoning, not just implemented.
- The repo is reproducible: a fresh clone plus documented setup steps can reproduce the eval numbers.

---

## 11. Open Questions / Decisions Needed Before Build

- Final selection of the 3-5 target apps/websites (should be a mix of layouts/complexity, and should be stable enough not to change their UI mid-project).
- Whether OmniParser runs acceptably within the 4GB VRAM budget, or whether the OpenCV-based fallback detector is needed from the start.
- Exact schema for the structured step log (needed early, since eval, demo generation, and debugging all depend on it).
- Whether the verifier is a separate model call or a lightweight rule-based check for Phase 1 (a full learned verifier may be Phase 2 scope).
