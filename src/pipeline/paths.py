#!/usr/bin/env python3
"""
Generic path resolution for the evaluation pipeline.

This module provides a unified way to resolve paths for any experiment.
All pipeline scripts should use this module instead of hardcoding paths.

Usage:
    from pipeline.paths import ExperimentPaths

    paths = ExperimentPaths("lab03-filmnow/runs/gemini31pro/run1")
    print(paths.rubric)
    print(paths.results_gold_standard)
    print(paths.submissions_dir)
"""

from __future__ import annotations

import argparse
from pathlib import Path


# Project root: parent of the src/pipeline/ directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = PROJECT_ROOT / "data"


class ExperimentPaths:
    """Resolves all paths for a given experiment under data/."""

    def __init__(self, experiment_name: str):
        self.experiment_name = experiment_name.strip().strip("/")
        self.project_root = PROJECT_ROOT
        self.experiment_dir = DATA_ROOT / self.experiment_name

        if not self.experiment_dir.exists():
            raise FileNotFoundError(
                f"Experiment directory not found: {self.experiment_dir}\n"
                f"Available experiments: {self._list_experiments()}"
            )

    # --- Prompt materials (templates, schemas, injected protocol text) ---

    @property
    def evaluation_principles(self) -> Path:
        return self.project_root / "src" / "prompt" / "evaluation_principles.md"

    @property
    def feedback_style_guide(self) -> Path:
        return self.project_root / "src" / "prompt" / "feedback_style_guide.md"

    @property
    def abstract_calibration(self) -> Path:
        return self.project_root / "src" / "prompt" / "abstract_calibration.md"

    @property
    def prompt_template_stage1(self) -> Path:
        return self.project_root / "src" / "prompt" / "template_stage1.md"

    @property
    def prompt_template_stage2(self) -> Path:
        return self.project_root / "src" / "prompt" / "template_stage2.md"

    @property
    def schema_stage1(self) -> Path:
        return self.project_root / "src" / "prompt" / "schema_stage1.json"

    @property
    def schema_stage2(self) -> Path:
        return self.project_root / "src" / "prompt" / "schema_stage2.json"

    # --- Experiment-specific config ---

    @property
    def experiment_config(self) -> Path:
        return self.experiment_dir / "experiment_config.json"

    @property
    def rubric(self) -> Path:
        return self.experiment_dir / "inputs" / "assignment" / "rubric.json"

    @property
    def lab_specification(self) -> Path:
        return self.experiment_dir / "inputs" / "assignment" / "lab_specification.md"

    @property
    def grading_reference(self) -> Path:
        return self.experiment_dir / "inputs" / "assignment" / "grading_reference.md"

    @property
    def starter_scaffold(self) -> Path:
        return self.experiment_dir / "inputs" / "assignment" / "starter_scaffold.md"

    @property
    def gold_standard_calibration(self) -> Path:
        return self.experiment_dir / "inputs" / "assignment" / "gold_standard_calibration.md"

    # --- Input artifacts ---

    @property
    def inputs_dir(self) -> Path:
        return self.experiment_dir / "inputs"

    @property
    def assignment_dir(self) -> Path:
        return self.inputs_dir / "assignment"

    @property
    def data_dir(self) -> Path:
        """Backward-compatible alias for canonical input artifacts."""
        return self.inputs_dir

    @property
    def imports_dir(self) -> Path:
        return self.inputs_dir / "imports"

    @property
    def manifests_dir(self) -> Path:
        return self.inputs_dir / "manifests"

    @property
    def submissions_dir(self) -> Path:
        return self.inputs_dir / "submissions"

    # --- Prompt artifacts ---

    @property
    def prompts_dir(self) -> Path:
        return self.experiment_dir / "prompts"

    @property
    def rendered_prompts_dir(self) -> Path:
        return self.prompts_dir / "rendered"

    @property
    def official_sample(self) -> Path:
        return self.manifests_dir / "official_sample.json"

    @property
    def anonymization_map(self) -> Path:
        return self.manifests_dir / "anonymization_map.private.json"

    @property
    def analysis_cohort(self) -> Path:
        return self.manifests_dir / "analysis_cohort.json"

    @property
    def baseline_snapshot(self) -> Path:
        return self.manifests_dir / "baseline_snapshot.json"

    # --- Output artifacts ---

    @property
    def outputs_dir(self) -> Path:
        return self.experiment_dir / "outputs"

    @property
    def results_dir(self) -> Path:
        """Backward-compatible alias for canonical output artifacts."""
        return self.outputs_dir

    @property
    def results_gold_standard(self) -> Path:
        """Directory holding the high-fidelity, manually refined gold-standard evaluation JSONs."""
        return self.results_dir / "gold_standard"

    @property
    def results_human(self) -> Path:
        """Directory holding the original monitor/human evaluations (non-refined)."""
        return self.results_dir / "human"

    @property
    def results_monitor(self) -> Path:
        """Alias for results_human."""
        return self.results_human

    @property
    def results_ground_truth(self) -> Path:
        """Canonical ground truth for LLM evaluation (points to gold_standard)."""
        return self.results_gold_standard

    @property
    def results_llm(self) -> Path:
        return self.results_dir / "llm"

    @property
    def results_raw_api(self) -> Path:
        return self.results_dir / "raw_api"

    @property
    def results_raw_parsed(self) -> Path:
        return self.results_dir / "raw_parsed"

    @property
    def results_normalized(self) -> Path:
        return self.results_dir / "normalized"

    @property
    def results_consolidated(self) -> Path:
        return self.results_dir / "consolidated"

    @property
    def results_analysis(self) -> Path:
        return self.experiment_dir / "analyses"

    @property
    def results_figures(self) -> Path:
        return self.results_analysis / "figures"

    # --- Submissions root (external clones) ---

    def resolve_submissions_root(self, config: dict | None = None) -> Path:
        """Resolve the path to the external submissions directory."""
        if config is None:
            import json
            config = json.loads(self.experiment_config.read_text(encoding="utf-8"))
        rel = config.get("submissions_root", "../../laboratorio-3-submissions")
        return (self.experiment_dir / rel).resolve()

    def resolve_repo_path(self, original_path: str) -> Path:
        """Resolve a manifest's original_path to an absolute path."""
        return (self.experiment_dir / original_path).resolve()

    # --- Utilities ---

    def _list_experiments(self) -> list[str]:
        """List experiment dirs under data/ that contain experiment_config.json."""
        if not DATA_ROOT.exists():
            return []
        found: list[str] = []
        for config in DATA_ROOT.rglob("experiment_config.json"):
            found.append(str(config.parent.relative_to(DATA_ROOT)))
        return sorted(found)

    def __repr__(self) -> str:
        return f"ExperimentPaths('{self.experiment_name}')"


def add_experiment_argument(parser: argparse.ArgumentParser):
    """Add the --experiment argument to an argparse parser."""
    parser.add_argument(
        "--experiment", "-e",
        required=True,
        help="Experiment path under data/ (e.g. lab03-filmnow/runs/gpt55/run1)",
    )


def get_paths_from_args(args: argparse.Namespace) -> ExperimentPaths:
    """Create ExperimentPaths from parsed arguments."""
    return ExperimentPaths(args.experiment)
