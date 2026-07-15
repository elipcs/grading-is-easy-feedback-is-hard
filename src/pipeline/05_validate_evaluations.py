#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, add_experiment_argument

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def artifact_path(path):
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


def expected_submission_ids(paths):
    if paths.analysis_cohort.exists():
        cohort = load_json(paths.analysis_cohort)
        ids = cohort.get("strict_submission_ids", [])
        if ids:
            return sorted(ids)
    official = load_json(paths.official_sample)["entries"]
    pretest_path = paths.manifests_dir / "pretest_sample.json"
    pretest = load_json(pretest_path)["entries"] if pretest_path.exists() else []
    return sorted([entry["submission_id"] for entry in official + pretest])


def rubric_index(paths):
    rubric = load_json(paths.rubric)
    if not rubric.get("rubric_ready"):
        raise SystemExit("config/rubric.json has not been filled out yet.")
    criteria = rubric["criteria"]
    index = {criterion["id"]: criterion for criterion in criteria}
    total_max = float(rubric.get("score_model", {}).get("total_max_score", 10.0))
    return index, total_max


def weighted_total_score(criteria_results, rubric_by_id, expected_total_max):
    total = 0.0
    for criterion_result in criteria_results:
        criterion_id = criterion_result.get("criterion_id")
        rubric_criterion = rubric_by_id.get(criterion_id)
        if not rubric_criterion:
            continue
        weight = float(rubric_criterion.get("weight", 1.0))
        score = float(criterion_result.get("score", 0))
        total += score * weight
    return min(round(total, 4), expected_total_max)


def is_blank_human_template(payload):
    if payload.get("evaluator_type") != "human":
        return False

    if str(payload.get("student_feedback", "") or "").strip():
        return False

    for criterion in payload.get("criteria", []):
        if float(criterion.get("score", 0)) != 0:
            return False
        if str(criterion.get("justification", "") or "").strip():
            return False
        if criterion.get("evidence_refs"):
            return False
    return True


def validate_deductions(criterion_result, criterion_id, expected_max, evaluator_type, errors, warnings):
    score = float(criterion_result.get("score", 0))
    expected_loss = round(expected_max - score, 4)
    deductions = criterion_result.get("deductions", [])

    if deductions is None:
        deductions = []
    if not isinstance(deductions, list):
        errors.append(f"deductions must be a list in criterion {criterion_id}")
        return

    total_points_lost = 0.0
    for index, deduction in enumerate(deductions, start=1):
        if not isinstance(deduction, dict):
            errors.append(f"invalid deduction in criterion {criterion_id} at position {index}")
            continue

        for field_name in ("problem", "consequence", "how_to_fix"):
            value = deduction.get(field_name, "")
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{field_name} empty in deductions for criterion {criterion_id}")

        evidence_refs = deduction.get("evidence_refs", [])
        if not isinstance(evidence_refs, list):
            errors.append(f"invalid evidence_refs in deductions for criterion {criterion_id}")
        elif evaluator_type == "llm" and not evidence_refs:
            errors.append(f"missing evidence_refs in deductions for criterion {criterion_id}")
        elif not evidence_refs:
            warnings.append(f"missing evidence_refs in deductions for criterion {criterion_id}")

        points_lost = deduction.get("points_lost")
        if not isinstance(points_lost, (int, float)):
            errors.append(f"invalid points_lost in deductions for criterion {criterion_id}")
            continue
        if float(points_lost) <= 0:
            errors.append(f"points_lost must be positive in deductions for criterion {criterion_id}")
            continue
        total_points_lost += float(points_lost)

    if evaluator_type == "llm":
        if expected_loss > 1e-6 and not deductions:
            errors.append(f"missing deductions for criterion {criterion_id} despite point loss")
        elif expected_loss <= 1e-6 and deductions:
            warnings.append(f"deductions reported for criterion {criterion_id} without point loss")
        elif deductions and abs(total_points_lost - expected_loss) > 0.05:
            errors.append(
                f"sum of points_lost in deductions does not match criterion loss for {criterion_id}"
            )


def validate_feedback_items(payload, evaluator_type, rubric_by_id, errors, warnings):
    feedback_items = payload.get("feedback_items", [])
    if feedback_items is None:
        feedback_items = []
    if not isinstance(feedback_items, list):
        errors.append("feedback_items must be a list")
        return

    if evaluator_type == "llm" and not feedback_items:
        return

    for index, item in enumerate(feedback_items, start=1):
        if not isinstance(item, dict):
            errors.append(f"invalid feedback_item at position {index}")
            continue

        criterion_id = str(item.get("criterion_id", "") or "").strip()
        if evaluator_type == "llm" and not criterion_id:
            errors.append(f"empty criterion_id in feedback_items at position {index}")
        elif criterion_id and criterion_id not in rubric_by_id:
            warnings.append(f"criterion_id out of rubric in feedback_items at position {index}: {criterion_id}")

        for field_name in ("problem", "consequence", "how_to_fix"):
            value = item.get(field_name, "")
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{field_name} empty in feedback_items at position {index}")

        evidence_refs = item.get("evidence_refs", [])
        if not isinstance(evidence_refs, list):
            errors.append(f"invalid evidence_refs in feedback_items at position {index}")
        elif evaluator_type == "llm" and not evidence_refs:
            errors.append(f"missing evidence_refs in feedback_items at position {index}")
        elif not evidence_refs:
            warnings.append(f"missing evidence_refs in feedback_items at position {index}")


def validate_file(path, evaluator_type, submission_id, rubric_by_id, expected_total_max, confidence_labels):
    payload = load_json(path)
    errors = []
    warnings = []
    actual_evaluator_type = payload.get("evaluator_type")
    allowed_evaluator_types = {"expert", "human"} if evaluator_type == "human" else {evaluator_type}

    if is_blank_human_template(payload):
        return {
            "submission_id": submission_id,
            "evaluator_type": evaluator_type,
            "path": artifact_path(path),
            "status": "pending",
            "valid": False,
            "errors": [],
            "warnings": ["human report not filled out yet"],
        }

    if payload.get("submission_id") != submission_id:
        errors.append("submission_id diverges from filename")
    if actual_evaluator_type not in allowed_evaluator_types:
        errors.append("divergent evaluator_type")

    criteria = payload.get("criteria")
    if not isinstance(criteria, list):
        errors.append("criteria must be a list")
        criteria = []

    seen = set()
    for criterion_result in criteria:
        criterion_id = criterion_result.get("criterion_id")
        if criterion_id not in rubric_by_id:
            errors.append(f"invalid criterion_id: {criterion_id}")
            continue
        if criterion_id in seen:
            errors.append(f"duplicate criterion_id: {criterion_id}")
        seen.add(criterion_id)

        rubric_criterion = rubric_by_id[criterion_id]
        expected_max = float(rubric_criterion["max_score"])
        score = criterion_result.get("score")
        max_score = criterion_result.get("max_score")

        if max_score != expected_max:
            errors.append(f"divergent max_score for criterion {criterion_id}")
        if not isinstance(score, (int, float)):
            errors.append(f"invalid score for criterion {criterion_id}")
            continue
        if score < 0 or score > expected_max:
            errors.append(f"score out of range for criterion {criterion_id}")

        justification = criterion_result.get("justification", "")
        evidence_refs = criterion_result.get("evidence_refs", [])
        if not isinstance(justification, str) or not justification.strip():
            errors.append(f"empty justification for criterion {criterion_id}")
        if not isinstance(evidence_refs, list):
            errors.append(f"invalid evidence_refs for criterion {criterion_id}")
        elif not evidence_refs:
            warnings.append(f"missing evidence_refs for criterion {criterion_id}")

        validate_deductions(criterion_result, criterion_id, expected_max, evaluator_type, errors, warnings)

    missing = set(rubric_by_id.keys()) - seen
    if missing:
        errors.append("missing criteria: " + ", ".join(sorted(missing)))

    total_score = payload.get("total_score")
    total_max_score = payload.get("total_max_score")
    if total_max_score != expected_total_max:
        errors.append("total_max_score diverges from rubric")
    if not isinstance(total_score, (int, float)):
        errors.append("invalid total_score")
    else:
        calculated_total = weighted_total_score(criteria, rubric_by_id, expected_total_max)
        if abs(float(total_score) - calculated_total) > 1e-6:
            errors.append("total_score does not match the weighted sum of criteria")

    student_feedback = payload.get("student_feedback", "")
    if (
        evaluator_type == "human"
        and actual_evaluator_type == "human"
        and (not isinstance(student_feedback, str) or not student_feedback.strip())
    ):
        errors.append("empty student_feedback")

    validate_feedback_items(payload, evaluator_type, rubric_by_id, errors, warnings)

    confidence = payload.get("confidence")
    if confidence is not None and confidence not in confidence_labels:
        errors.append("confidence out of controlled vocabulary")

    return {
        "submission_id": submission_id,
        "evaluator_type": evaluator_type,
        "path": artifact_path(path),
        "status": "valid" if not errors and not warnings else ("usable_with_warnings" if not errors else "invalid"),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Validates the format and consistency of evaluations.")
    add_experiment_argument(parser)
    parser.add_argument(
        "--allow-invalid-human",
        action="store_true",
        help="Do not fail when human baseline has invalid files.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    paths = ExperimentPaths(args.experiment)
    config = load_json(paths.experiment_config)
    rubric_by_id, total_max = rubric_index(paths)
    submission_ids = expected_submission_ids(paths)

    result_dirs = {
        "human": paths.results_gold_standard,
        "llm": paths.results_llm,
    }

    reports = []
    for evaluator_type, result_dir in result_dirs.items():
        result_dir.mkdir(parents=True, exist_ok=True)
        for submission_id in submission_ids:
            path = result_dir / f"{submission_id}.json"
            if not path.exists():
                reports.append(
                    {
                        "submission_id": submission_id,
                        "evaluator_type": evaluator_type,
                        "path": artifact_path(path),
                        "status": "missing",
                        "valid": False,
                        "errors": ["file not found"],
                        "warnings": [],
                    }
                )
                continue
            reports.append(
                validate_file(
                    path,
                    evaluator_type,
                    submission_id,
                    rubric_by_id,
                    total_max,
                    config["confidence_labels"],
                )
            )

    summary = {
        "total_reports": len(reports),
        "valid_reports": sum(1 for report in reports if report["status"] == "valid"),
        "usable_with_warnings": sum(1 for report in reports if report["status"] == "usable_with_warnings"),
        "pending_reports": sum(1 for report in reports if report["status"] == "pending"),
        "missing_reports": sum(1 for report in reports if report["status"] == "missing"),
        "invalid_reports": sum(1 for report in reports if report["status"] == "invalid"),
        "reports": reports,
    }
    output_path = paths.results_analysis / "validation_report.json"
    write_json(output_path, summary)
    print(f"Report saved to: {output_path}")
    print(f"Valid files: {summary['valid_reports']}")
    print(f"Usable files with warnings: {summary['usable_with_warnings']}")
    print(f"Pending reports: {summary['pending_reports']}")
    print(f"Missing reports: {summary['missing_reports']}")
    print(f"Invalid reports: {summary['invalid_reports']}")

    invalid_human_reports = [
        report
        for report in reports
        if report["evaluator_type"] == "human" and report["status"] in {"invalid", "missing", "pending"}
    ]
    if invalid_human_reports and not args.allow_invalid_human:
        raise SystemExit(
            "Human baseline contains invalid/missing/pending files in analysis cohort. "
            "Fix baseline first or rerun with --allow-invalid-human."
        )


if __name__ == "__main__":
    main()
