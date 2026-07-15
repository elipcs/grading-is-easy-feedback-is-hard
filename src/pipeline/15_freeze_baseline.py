#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, add_experiment_argument

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def artifact_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Freeze baseline artifacts and create a canonical analysis cohort."
    )
    add_experiment_argument(parser)
    return parser.parse_args()


def main():
    args = parse_args()
    paths = ExperimentPaths(args.experiment)

    config = load_json(paths.experiment_config)
    official_payload = load_json(paths.official_sample)
    official_ids = sorted(entry["submission_id"] for entry in official_payload.get("entries", []))

    human_dir = paths.results_gold_standard
    llm_dir = paths.results_llm

    cohort_entries = []
    for submission_id in official_ids:
        cohort_entries.append(
            {
                "submission_id": submission_id,
                "has_human": (human_dir / f"{submission_id}.json").exists(),
                "has_llm": (llm_dir / f"{submission_id}.json").exists(),
            }
        )

    strict_ids = sorted(
        entry["submission_id"]
        for entry in cohort_entries
        if entry["has_human"] and entry["has_llm"]
    )

    analysis_cohort = {
        "experiment_id": config.get("experiment_id", args.experiment),
        "cohort_policy": "official_sample_with_human_and_llm",
        "official_sample_size": len(official_ids),
        "strict_cohort_size": len(strict_ids),
        "strict_submission_ids": strict_ids,
        "entries": cohort_entries,
    }
    write_json(paths.analysis_cohort, analysis_cohort)

    baseline_snapshot = {
        "experiment_id": config.get("experiment_id", args.experiment),
        "baseline_artifacts": {
            "experiment_config": artifact_path(paths.experiment_config),
            "validation_report": artifact_path(paths.results_analysis / "validation_report.json"),
            "quantitative_summary": artifact_path(paths.results_analysis / "quantitative_summary.json"),
        },
        "counts": {
            "official_sample_size": len(official_ids),
            "strict_cohort_size": len(strict_ids),
        },
    }
    write_json(paths.baseline_snapshot, baseline_snapshot)

    print(f"Saved cohort manifest: {paths.analysis_cohort}")
    print(f"Saved baseline snapshot: {paths.baseline_snapshot}")


if __name__ == "__main__":
    main()
