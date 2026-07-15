#!/usr/bin/env python3

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, add_experiment_argument


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_results(result_dir):
    results = {}
    for path in sorted(result_dir.glob("*.json")):
        payload = load_json(path)
        results[payload["submission_id"]] = payload
    return results


def mean(values):
    return sum(values) / len(values) if values else None





def safe_float(value):
    return float(value)


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


def official_submission_ids(paths):
    if paths.analysis_cohort.exists():
        cohort = load_json(paths.analysis_cohort)
        ids = cohort.get("strict_submission_ids", [])
        if ids:
            return set(ids)
    official = load_json(paths.official_sample)["entries"]
    return {entry["submission_id"] for entry in official}


def parse_args():
    parser = argparse.ArgumentParser(description="Calcula metricas de concordancia.")
    add_experiment_argument(parser)
    return parser.parse_args()


def main():
    args = parse_args()
    paths = ExperimentPaths(args.experiment)
    human = load_results(paths.results_gold_standard)
    llm = load_results(paths.results_llm)
    official_ids = official_submission_ids(paths)

    condition_payloads = {
        "llm": llm,
    }

    summary = {}
    criterion_breakdown = defaultdict(dict)

    for condition, llm_results in condition_payloads.items():
        total_abs_errors = []
        exact_agreements = []
        human_totals = []
        llm_totals = []
        unsupported_criteria = 0
        all_llm_criteria = 0

        per_criterion_errors = defaultdict(list)
        per_criterion_exact = defaultdict(list)

        for submission_id, human_payload in human.items():
            if submission_id not in official_ids:
                continue
            if not is_completed_human_payload(human_payload):
                continue
            llm_payload = llm_results.get(submission_id)
            if not llm_payload:
                continue

            human_total = safe_float(human_payload["total_score"])
            llm_total = safe_float(llm_payload["total_score"])
            total_abs_errors.append(abs(human_total - llm_total))
            human_totals.append(human_total)
            llm_totals.append(llm_total)

            human_by_criterion = {
                criterion["criterion_id"]: criterion for criterion in human_payload.get("criteria", [])
            }

            for llm_criterion in llm_payload.get("criteria", []):
                criterion_id = llm_criterion["criterion_id"]
                human_criterion = human_by_criterion.get(criterion_id)
                if not human_criterion:
                    continue

                llm_score = safe_float(llm_criterion["score"])
                human_score = safe_float(human_criterion["score"])
                error = abs(human_score - llm_score)

                per_criterion_errors[criterion_id].append(error)
                per_criterion_exact[criterion_id].append(1 if error == 0 else 0)
                exact_agreements.append(1 if error == 0 else 0)

                evidence_refs = llm_criterion.get("evidence_refs", [])
                if not evidence_refs:
                    unsupported_criteria += 1
                all_llm_criteria += 1

        summary[condition] = {
            "mean_absolute_error_total": mean(total_abs_errors),
            "exact_agreement_rate": mean(exact_agreements),
            "score_delta_stddev": (
                math.sqrt(mean([(value - mean(total_abs_errors)) ** 2 for value in total_abs_errors]))
                if total_abs_errors
                else None
            ),
            "unsupported_justification_rate": (
                unsupported_criteria / all_llm_criteria if all_llm_criteria else None
            ),
            "n_submissions_compared": len(total_abs_errors),
        }

        for criterion_id, errors in per_criterion_errors.items():
            criterion_breakdown[criterion_id][condition] = {
                "mean_absolute_error": mean(errors),
                "exact_agreement_rate": mean(per_criterion_exact[criterion_id]),
                "n": len(errors),
            }

    output_dir = paths.results_analysis
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "quantitative_summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "condition_summary": summary,
                "criterion_breakdown": criterion_breakdown,
            },
            handle,
            ensure_ascii=True,
            indent=2,
        )
        handle.write("\n")

    csv_rows = []
    for criterion_id, condition_data in sorted(criterion_breakdown.items()):
        for condition, values in sorted(condition_data.items()):
            csv_rows.append(
                {
                    "criterion_id": criterion_id,
                    "condition": condition,
                    "mean_absolute_error": values["mean_absolute_error"],
                    "exact_agreement_rate": values["exact_agreement_rate"],
                    "n": values["n"],
                }
            )

    csv_path = output_dir / "criterion_metrics.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "criterion_id",
                "condition",
                "mean_absolute_error",
                "exact_agreement_rate",
                "n",
            ],
        )
        writer.writeheader()
        writer.writerows(csv_rows)

    markdown_lines = [
        "# Resumo Quantitativo",
        "",
    ]
    for condition, values in summary.items():
        markdown_lines.extend(
            [
                f"## {condition}",
                "",
                f"- n_submissions_compared: {values['n_submissions_compared']}",
                f"- mean_absolute_error_total: {values['mean_absolute_error_total']}",
                f"- exact_agreement_rate: {values['exact_agreement_rate']}",
                f"- score_delta_stddev: {values['score_delta_stddev']}",
                f"- unsupported_justification_rate: {values['unsupported_justification_rate']}",
                "",
            ]
        )
    (output_dir / "quantitative_summary.md").write_text("\n".join(markdown_lines), encoding="utf-8")

    print(f"Resumo quantitativo salvo em: {summary_path}")
    print(f"Metricas por criterio salvas em: {csv_path}")


if __name__ == "__main__":
    main()
