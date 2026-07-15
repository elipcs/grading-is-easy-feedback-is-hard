#!/usr/bin/env python3

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, add_experiment_argument


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def manifest_map(paths):
    official = load_json(paths.official_sample)["entries"]
    pretest_path = paths.manifests_dir / "pretest_sample.json"
    pretest = load_json(pretest_path)["entries"] if pretest_path.exists() else []
    return {entry["submission_id"]: entry for entry in official + pretest}


def official_submission_ids(paths):
    if paths.analysis_cohort.exists():
        cohort = load_json(paths.analysis_cohort)
        ids = cohort.get("strict_submission_ids", [])
        if ids:
            return set(ids)
    official = load_json(paths.official_sample)["entries"]
    return {entry["submission_id"] for entry in official}


def is_completed_human_payload(payload):
    if payload.get("evaluator_type") != "human":
        return True
    if str(payload.get("student_feedback", "") or "").strip():
        return True
    for criterion in payload.get("criteria", []):
        if float(criterion.get("score", 0)) != 0:
            return True
        if str(criterion.get("justification", "") or "").strip():
            return True
        if criterion.get("evidence_refs"):
            return True
    return False


def load_results(paths):
    result_dirs = {
        "human": paths.results_gold_standard,
        "llm": paths.results_llm,
    }
    data = {}
    for evaluator_type, result_dir in result_dirs.items():
        data[evaluator_type] = {}
        if not result_dir.exists():
            continue
        for path in sorted(result_dir.glob("*.json")):
            payload = load_json(path)
            data[evaluator_type][payload["submission_id"]] = payload
    return data


def parse_args():
    parser = argparse.ArgumentParser(description="Consolida resultados em CSVs.")
    add_experiment_argument(parser)
    return parser.parse_args()


def main():
    args = parse_args()
    paths = ExperimentPaths(args.experiment)
    manifests = manifest_map(paths)
    official_ids = official_submission_ids(paths)
    results = load_results(paths)

    long_rows = []
    summary_rows = []
    divergence_rows = []

    for evaluator_type, payloads in results.items():
        for submission_id, payload in sorted(payloads.items()):
            manifest = manifests.get(submission_id, {})
            summary_rows.append(
                {
                    "submission_id": submission_id,
                    "role": manifest.get("role", ""),
                    "evaluator_type": evaluator_type,
                    "total_score": payload.get("total_score"),
                    "total_max_score": payload.get("total_max_score"),
                    "confidence": payload.get("confidence"),
                    "original_repository": manifest.get("original_repository", ""),
                }
            )

            for criterion in payload.get("criteria", []):
                long_rows.append(
                    {
                        "submission_id": submission_id,
                        "role": manifest.get("role", ""),
                        "original_repository": manifest.get("original_repository", ""),
                        "evaluator_type": evaluator_type,
                        "criterion_id": criterion.get("criterion_id"),
                        "criterion_name": criterion.get("criterion_name"),
                        "score": criterion.get("score"),
                        "max_score": criterion.get("max_score"),
                        "justification": criterion.get("justification"),
                        "evidence_refs": " | ".join(criterion.get("evidence_refs", [])),
                        "confidence": payload.get("confidence"),
                    }
                )

    human_results = results.get("human", {})
    for condition in ("llm",):
        for submission_id, llm_payload in sorted(results.get(condition, {}).items()):
            if submission_id not in official_ids:
                continue
            human_payload = human_results.get(submission_id)
            if not human_payload:
                continue
            if not is_completed_human_payload(human_payload):
                continue
            human_by_criterion = {
                criterion["criterion_id"]: criterion for criterion in human_payload.get("criteria", [])
            }
            for llm_criterion in llm_payload.get("criteria", []):
                criterion_id = llm_criterion["criterion_id"]
                human_criterion = human_by_criterion.get(criterion_id)
                if not human_criterion:
                    continue
                divergence_rows.append(
                    {
                        "submission_id": submission_id,
                        "role": manifests.get(submission_id, {}).get("role", ""),
                        "condition": condition,
                        "criterion_id": criterion_id,
                        "criterion_name": llm_criterion.get("criterion_name"),
                        "human_score": human_criterion.get("score"),
                        "llm_score": llm_criterion.get("score"),
                        "absolute_delta": abs(float(human_criterion.get("score", 0)) - float(llm_criterion.get("score", 0))),
                        "divergence_category": "",
                        "notes": "",
                    }
                )

    consolidated_dir = paths.results_consolidated
    analysis_dir = paths.results_analysis

    write_csv(
        consolidated_dir / "evaluations_long.csv",
        long_rows,
        [
            "submission_id",
            "role",
            "original_repository",
            "evaluator_type",
            "criterion_id",
            "criterion_name",
            "score",
            "max_score",
            "justification",
            "evidence_refs",
            "confidence",
        ],
    )
    write_csv(
        consolidated_dir / "evaluations_summary.csv",
        summary_rows,
        [
            "submission_id",
            "role",
            "evaluator_type",
            "total_score",
            "total_max_score",
            "confidence",
            "original_repository",
        ],
    )
    write_csv(
        analysis_dir / "divergence_coding_template.csv",
        divergence_rows,
        [
            "submission_id",
            "role",
            "condition",
            "criterion_id",
            "criterion_name",
            "human_score",
            "llm_score",
            "absolute_delta",
            "divergence_category",
            "notes",
        ],
    )

    print(f"CSV longo salvo em: {consolidated_dir / 'evaluations_long.csv'}")
    print(f"CSV resumo salvo em: {consolidated_dir / 'evaluations_summary.csv'}")
    print(f"Template qualitativo salvo em: {analysis_dir / 'divergence_coding_template.csv'}")


if __name__ == "__main__":
    main()
