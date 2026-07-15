#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import PROJECT_ROOT
from pipeline.utils.determinism import (
    all_runs,
    extract_grade_vector,
    extract_problem_sets,
    load_json,
    load_llm_outputs,
    load_run_analysis_metrics,
    load_study_manifest,
    pairwise_feedback_metrics,
    pairwise_grade_metrics,
    problem_overlap,
    triple_run_stability,
    write_json,
)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def build_pairwise_summaries(run_outputs: dict[str, dict[str, dict]], labels: list[str]) -> list[dict]:
    summaries = []
    for left, right in combinations(labels, 2):
        grade = pairwise_grade_metrics(run_outputs[left], run_outputs[right])
        feedback = pairwise_feedback_metrics(run_outputs[left], run_outputs[right])
        summaries.append(
            {
                "comparison": f"{left}_vs_{right}",
                "left_run": left,
                "right_run": right,
                **grade,
                **feedback,
            }
        )
    return summaries


def build_submission_rows(
    run_outputs: dict[str, dict[str, dict]],
    labels: list[str],
    experiments: dict[str, str],
) -> list[dict]:
    shared_ids = sorted(set.intersection(*(set(outputs) for outputs in run_outputs.values())))
    rows = []
    for submission_id in shared_ids:
        grades = {
            label: extract_grade_vector(run_outputs[label][submission_id])["total_score"]
            for label in labels
        }
        row = {
            "submission_id": submission_id,
            **{f"{label}_total_score": grades[label] for label in labels},
        }
        if len(labels) >= 2:
            row["run1_run2_delta"] = grades[labels[1]] - grades[labels[0]]
        if len(labels) >= 3:
            row["run1_run3_delta"] = grades[labels[2]] - grades[labels[0]]
            row["run2_run3_delta"] = grades[labels[2]] - grades[labels[1]]
            row["triple_exact_total_score_match"] = int(
                grades[labels[0]] == grades[labels[1]] == grades[labels[2]]
            )
            row["run1_run2_problem_jaccard"] = problem_overlap(
                run_outputs[labels[0]][submission_id],
                run_outputs[labels[1]][submission_id],
            )
            row["run1_run3_problem_jaccard"] = problem_overlap(
                run_outputs[labels[0]][submission_id],
                run_outputs[labels[2]][submission_id],
            )
            row["run2_run3_problem_jaccard"] = problem_overlap(
                run_outputs[labels[1]][submission_id],
                run_outputs[labels[2]][submission_id],
            )
            hashes = [
                extract_problem_sets(run_outputs[label][submission_id])["student_feedback_hash"]
                for label in labels
            ]
            row["triple_exact_student_feedback_hash_match"] = int(
                hashes[0] == hashes[1] == hashes[2]
            )
        rows.append(row)
    return rows


def build_criterion_rows(run_outputs: dict[str, dict[str, dict]], labels: list[str]) -> list[dict]:
    criterion_ids = set()
    for outputs in run_outputs.values():
        for payload in outputs.values():
            criterion_ids.update(extract_grade_vector(payload)["criteria"].keys())

    shared_ids = sorted(set.intersection(*(set(outputs) for outputs in run_outputs.values())))
    rows = []
    for criterion_id in sorted(criterion_ids):
        exact_matches = 0
        compared = 0
        per_label_values = {label: [] for label in labels}
        for submission_id in shared_ids:
            scores = []
            valid = True
            for label in labels:
                score = extract_grade_vector(run_outputs[label][submission_id])["criteria"].get(criterion_id)
                if score is None:
                    valid = False
                    break
                scores.append(score)
                per_label_values[label].append(score)
            if not valid:
                continue
            compared += 1
            if scores.count(scores[0]) == len(scores):
                exact_matches += 1

        row = {
            "criterion_id": criterion_id,
            "compared_submissions": compared,
            "exact_score_match_count": exact_matches,
            "exact_score_match_rate": (exact_matches / compared) if compared else None,
        }
        for label in labels:
            values = per_label_values[label]
            row[f"{label}_mean_score"] = (sum(values) / len(values)) if values else None
        rows.append(row)
    return rows


def build_run_summaries(manifest: dict, runs: list[dict], run_outputs: dict[str, dict[str, dict]]) -> list[dict]:
    summaries = []
    for entry in runs:
        label = entry["label"]
        experiment = entry["experiment"]
        outputs = run_outputs[label]
        scores = [extract_grade_vector(payload)["total_score"] for payload in outputs.values()]
        analysis = load_run_analysis_metrics(experiment)
        summaries.append(
            {
                "label": label,
                "experiment": experiment,
                "output_count": len(outputs),
                "mean_total_score": (sum(scores) / len(scores)) if scores else None,
                "analysis_available": analysis is not None,
                **(analysis or {}),
            }
        )
    return summaries


def render_markdown(payload: dict) -> str:
    lines = [
        "# Determinism Benchmark",
        "",
        f"Study: `{payload['study']}`",
        f"Model: `{payload.get('model', '-')}`",
        "",
        "## Run Coverage",
        "",
        "| run | experiment | outputs | mean total score | grade MAE vs expert | detection F1 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["run_summaries"]:
        lines.append(
            "| {label} | {experiment} | {output_count} | {mean_total_score} | {grade_mae} | {detection_f1} |".format(
                label=row["label"],
                experiment=row["experiment"],
                output_count=row["output_count"],
                mean_total_score=f"{row['mean_total_score']:.4f}" if row["mean_total_score"] is not None else "-",
                grade_mae=f"{row['grade_mae_vs_expert']:.4f}" if row.get("grade_mae_vs_expert") is not None else "-",
                detection_f1=f"{row['detection_f1']:.4f}" if row.get("detection_f1") is not None else "-",
            )
        )

    lines.extend(["", "## Pairwise Stability", ""])
    lines.append("| comparison | n | exact score match % | MAE | mean problem Jaccard |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for row in payload["pairwise_summaries"]:
        lines.append(
            "| {comparison} | {n} | {exact:.1%} | {mae:.4f} | {jaccard:.4f} |".format(
                comparison=row["comparison"],
                n=row["n"],
                exact=row["exact_match_rate"] or 0.0,
                mae=row["mae"] or 0.0,
                jaccard=row["mean_problem_jaccard"] or 0.0,
            )
        )

    triple = payload["triple_run_summary"]
    lines.extend(
        [
            "",
            "## Triple-Run Stability",
            "",
            f"- Compared submissions: {triple['n']}",
            f"- Exact total-score matches across all 3 runs: {triple['exact_total_score_matches']} "
            f"({(triple['exact_total_score_rate'] or 0.0):.1%})",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze grading determinism across repeated model runs.")
    parser.add_argument(
        "--study-manifest",
        required=True,
        help="Path to study manifest JSON (baseline + repeat experiments).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for determinism benchmark artifacts.",
    )
    parser.add_argument(
        "--min-outputs",
        type=int,
        default=1,
        help="Minimum outputs required per run before analysis (default: 1).",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Skip missing or underfilled runs instead of failing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_study_manifest(args.study_manifest)
    runs = all_runs(manifest)

    run_outputs = {}
    included_runs = []
    for entry in runs:
        outputs = load_llm_outputs(entry["experiment"])
        if len(outputs) < args.min_outputs:
            if args.allow_incomplete:
                print(f"Skipping {entry['label']} ({entry['experiment']}): only {len(outputs)} outputs.")
                continue
            raise SystemExit(
                f"Run {entry['label']} ({entry['experiment']}) has only {len(outputs)} outputs; "
                f"expected at least {args.min_outputs}."
            )
        run_outputs[entry["label"]] = outputs
        included_runs.append(entry)

    if len(included_runs) < 2:
        raise SystemExit(
            "At least two completed runs are required for determinism analysis. "
            f"Found {len(included_runs)} usable run(s)."
        )

    labels = [entry["label"] for entry in included_runs]

    pairwise_summaries = build_pairwise_summaries(run_outputs, labels)
    submission_rows = build_submission_rows(
        run_outputs,
        labels,
        {entry["label"]: entry["experiment"] for entry in included_runs},
    )
    criterion_rows = build_criterion_rows(run_outputs, labels)
    run_summaries = build_run_summaries(manifest, included_runs, run_outputs)
    triple_summary = triple_run_stability([run_outputs[label] for label in labels])

    payload = {
        "study": manifest.get("study"),
        "model": manifest.get("model"),
        "temperature": manifest.get("temperature"),
        "reasoning_effort": manifest.get("reasoning_effort"),
        "execution_mode": manifest.get("execution_mode"),
        "baseline_experiment": manifest["baseline_experiment"],
        "repeat_experiments": manifest["repeat_experiments"],
        "runs": included_runs,
        "run_summaries": run_summaries,
        "pairwise_summaries": pairwise_summaries,
        "triple_run_summary": triple_summary,
    }

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    write_json(output_dir / "determinism_benchmark.json", payload)
    write_csv(
        output_dir / "determinism_benchmark.csv",
        submission_rows,
        fieldnames=list(submission_rows[0].keys()) if submission_rows else ["submission_id"],
    )
    write_csv(
        output_dir / "determinism_by_criterion.csv",
        criterion_rows,
        fieldnames=list(criterion_rows[0].keys()) if criterion_rows else ["criterion_id"],
    )
    (output_dir / "determinism_benchmark.md").write_text(render_markdown(payload) + "\n", encoding="utf-8")

    print(f"Determinism benchmark JSON: {output_dir / 'determinism_benchmark.json'}")
    print(f"Determinism benchmark CSV: {output_dir / 'determinism_benchmark.csv'}")
    print(f"Determinism by criterion CSV: {output_dir / 'determinism_by_criterion.csv'}")
    print(f"Determinism benchmark MD: {output_dir / 'determinism_benchmark.md'}")


if __name__ == "__main__":
    main()
