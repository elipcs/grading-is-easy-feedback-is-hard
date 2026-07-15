#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from pathlib import Path

from pipeline.paths import ExperimentPaths, PROJECT_ROOT


REQUIRED_MANIFEST_KEYS = ("baseline_experiment", "repeat_experiments")


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def load_study_manifest(path: Path | str) -> dict:
    manifest_path = Path(path)
    if not manifest_path.is_absolute():
        manifest_path = PROJECT_ROOT / manifest_path
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError(f"Invalid study manifest: {manifest_path}")

    missing = [key for key in REQUIRED_MANIFEST_KEYS if key not in manifest]
    if missing:
        raise ValueError(f"Study manifest missing keys {missing}: {manifest_path}")

    repeats = manifest.get("repeat_experiments") or []
    if not isinstance(repeats, list) or len(repeats) < 2:
        raise ValueError("repeat_experiments must list at least two repeat experiment ids.")

    return manifest


def all_runs(manifest: dict) -> list[dict]:
    baseline = manifest["baseline_experiment"]
    runs = [{"label": "run1", "experiment": baseline}]
    for index, experiment in enumerate(manifest["repeat_experiments"], start=2):
        runs.append({"label": f"run{index}", "experiment": experiment})
    return runs


def run_labels(manifest: dict) -> list[str]:
    return [entry["label"] for entry in all_runs(manifest)]


def load_llm_outputs(experiment: str) -> dict[str, dict]:
    paths = ExperimentPaths(experiment)
    outputs = {}
    llm_dir = paths.results_llm
    if not llm_dir.exists():
        return outputs
    for path in sorted(llm_dir.glob("S*.json")):
        outputs[path.stem] = load_json(path)
    return outputs


def count_llm_outputs_safe(experiment: str) -> int:
    return len(load_llm_outputs(experiment))


def normalize_problem_text(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", (text or "").strip().lower())
    return collapsed


def extract_grade_vector(payload: dict) -> dict:
    criteria_scores = {}
    for criterion in payload.get("criteria", []):
        criterion_id = criterion.get("criterion_id")
        if criterion_id:
            criteria_scores[criterion_id] = float(criterion.get("score", 0.0))
    return {
        "total_score": float(payload.get("total_score", 0.0)),
        "criteria": criteria_scores,
    }


def extract_problem_sets(payload: dict) -> dict:
    problems = set()
    for criterion in payload.get("criteria", []):
        for deduction in criterion.get("deductions", []):
            problem = normalize_problem_text(deduction.get("problem", ""))
            if problem:
                problems.add(problem)

    feedback_items = []
    for item in payload.get("feedback_items", []):
        if isinstance(item, dict):
            text = item.get("problem") or item.get("message") or item.get("text") or ""
        else:
            text = str(item)
        normalized = normalize_problem_text(text)
        if normalized:
            feedback_items.append(normalized)

    student_feedback = payload.get("student_feedback") or ""
    feedback_hash = hashlib.sha256(student_feedback.encode("utf-8")).hexdigest()
    return {
        "problems": problems,
        "feedback_items": feedback_items,
        "feedback_item_count": len(payload.get("feedback_items", [])),
        "student_feedback_hash": feedback_hash,
    }


def problem_overlap(payload_a: dict, payload_b: dict) -> float:
    problems_a = extract_problem_sets(payload_a)["problems"]
    problems_b = extract_problem_sets(payload_b)["problems"]
    if not problems_a and not problems_b:
        return 1.0
    union = problems_a | problems_b
    if not union:
        return 1.0
    return len(problems_a & problems_b) / len(union)


def pairwise_grade_metrics(outputs_a: dict[str, dict], outputs_b: dict[str, dict]) -> dict:
    shared_ids = sorted(set(outputs_a) & set(outputs_b))
    if not shared_ids:
        return {
            "n": 0,
            "exact_match_count": 0,
            "exact_match_rate": None,
            "mae": None,
            "rmse": None,
            "max_abs_delta": None,
            "mean_signed_delta": None,
        }

    deltas = []
    exact = 0
    for submission_id in shared_ids:
        score_a = extract_grade_vector(outputs_a[submission_id])["total_score"]
        score_b = extract_grade_vector(outputs_b[submission_id])["total_score"]
        delta = score_b - score_a
        deltas.append(delta)
        if math.isclose(score_a, score_b, rel_tol=0.0, abs_tol=1e-9):
            exact += 1

    abs_deltas = [abs(delta) for delta in deltas]
    return {
        "n": len(shared_ids),
        "exact_match_count": exact,
        "exact_match_rate": exact / len(shared_ids),
        "mae": statistics.mean(abs_deltas),
        "rmse": math.sqrt(statistics.mean(delta * delta for delta in deltas)),
        "max_abs_delta": max(abs_deltas),
        "mean_signed_delta": statistics.mean(deltas),
    }


def pairwise_feedback_metrics(outputs_a: dict[str, dict], outputs_b: dict[str, dict]) -> dict:
    shared_ids = sorted(set(outputs_a) & set(outputs_b))
    if not shared_ids:
        return {
            "n": 0,
            "mean_problem_jaccard": None,
            "exact_student_feedback_hash_rate": None,
            "mean_feedback_item_count_delta": None,
        }

    jaccards = []
    exact_feedback_hashes = 0
    item_count_deltas = []
    for submission_id in shared_ids:
        meta_a = extract_problem_sets(outputs_a[submission_id])
        meta_b = extract_problem_sets(outputs_b[submission_id])
        jaccards.append(problem_overlap(outputs_a[submission_id], outputs_b[submission_id]))
        if meta_a["student_feedback_hash"] == meta_b["student_feedback_hash"]:
            exact_feedback_hashes += 1
        item_count_deltas.append(meta_b["feedback_item_count"] - meta_a["feedback_item_count"])

    return {
        "n": len(shared_ids),
        "mean_problem_jaccard": statistics.mean(jaccards),
        "exact_student_feedback_hash_rate": exact_feedback_hashes / len(shared_ids),
        "mean_feedback_item_count_delta": statistics.mean(item_count_deltas),
    }


def triple_run_stability(run_outputs: list[dict[str, dict]]) -> dict:
    if len(run_outputs) < 3:
        return {"n": 0, "exact_total_score_matches": 0, "exact_total_score_rate": None}

    shared_ids = sorted(set.intersection(*(set(outputs) for outputs in run_outputs)))
    if not shared_ids:
        return {"n": 0, "exact_total_score_matches": 0, "exact_total_score_rate": None}

    exact = 0
    for submission_id in shared_ids:
        scores = [
            extract_grade_vector(run_outputs[index][submission_id])["total_score"]
            for index in range(3)
        ]
        if all(math.isclose(scores[0], score, rel_tol=0.0, abs_tol=1e-9) for score in scores[1:]):
            exact += 1

    return {
        "n": len(shared_ids),
        "exact_total_score_matches": exact,
        "exact_total_score_rate": exact / len(shared_ids),
    }


def load_run_analysis_metrics(experiment: str) -> dict | None:
    paths = ExperimentPaths(experiment)
    grade = load_json(paths.results_analysis / "grade_comparison.json")
    overlap = load_json(paths.results_analysis / "error_overlap.json")
    if not grade and not overlap:
        return None
    overall_grade = (grade or {}).get("overall", {})
    global_overlap = (overlap or {}).get("global_metrics", {})
    return {
        "grade_mae_vs_expert": overall_grade.get("mae"),
        "grade_rmse_vs_expert": overall_grade.get("rmse"),
        "grade_bias_vs_expert": overall_grade.get("mean_bias"),
        "detection_precision": global_overlap.get("precision"),
        "detection_recall": global_overlap.get("recall"),
        "detection_f1": global_overlap.get("f1"),
    }


def find_missing_submission_ids(experiment: str, expected_count: int = 84) -> list[str]:
    present = set(load_llm_outputs(experiment))
    if expected_count <= 0:
        return []
    expected = {f"S{index:02d}" for index in range(1, expected_count + 1)}
    return sorted(expected - present)


def find_batch_stage1_errors(experiment: str) -> list[str]:
    paths = ExperimentPaths(experiment)
    batch_root = paths.results_raw_api / "batch_runs"
    if not batch_root.exists():
        return []

    latest_marker = load_json(batch_root / "latest_run.json")
    run_id = (latest_marker or {}).get("run_id")
    if not run_id:
        return []

    errors_path = batch_root / run_id / "stage1.processing_errors.json"
    errors = load_json(errors_path, []) or []
    return sorted({row.get("submission_id") for row in errors if row.get("submission_id")})


def submissions_needing_retry(experiment: str, expected_count: int = 84) -> list[str]:
    missing = set(find_missing_submission_ids(experiment, expected_count=expected_count))
    missing.update(find_batch_stage1_errors(experiment))
    return sorted(missing)
