"""Phase 3 check: eval/grounding.py runs end to end and emits a metrics JSON
with a hit-rate number."""

from pathlib import Path

from vlagui.eval.grounding import run


def test_grounding_eval_emits_hit_rate(tmp_path: Path) -> None:
    report_path = tmp_path / "grounding_eval.json"
    report = run(limit_per_split=5, report_path=report_path)

    assert report_path.exists()
    for benchmark in ("screenspot", "local_oracle"):
        for mode in ("raw", "som"):
            assert isinstance(report[benchmark][mode]["hit_rate"], float)
            assert report[benchmark][mode]["n"] > 0
