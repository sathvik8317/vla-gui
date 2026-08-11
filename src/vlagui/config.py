"""Central config: model names, viewport, step budget, paths."""

from pathlib import Path

from pydantic import BaseModel


class Viewport(BaseModel):
    width: int = 1280
    height: int = 800
    device_scale_factor: int = 1  # pinned so screenshot pixels == CSS pixels


class Settings(BaseModel):
    # "qwen3-vl:2b" (no suffix) resolves to Ollama's thinking-variant renderer/parser,
    # which burns its whole token budget on hidden <think> reasoning and returns an
    # empty "response" on anything but a trivial prompt. Use the instruct tag for
    # single-shot grounding calls.
    grounder_model: str = "qwen3-vl:2b-instruct"
    ollama_host: str = "http://localhost:11434"
    viewport: Viewport = Viewport()
    max_steps: int = 6

    root_dir: Path = Path(__file__).resolve().parents[2]
    tasks_dir: Path = root_dir / "tasks"
    reports_dir: Path = root_dir / "reports"
    data_dir: Path = root_dir / "data"

    model_config = {"arbitrary_types_allowed": True}


settings = Settings()
