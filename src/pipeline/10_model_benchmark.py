#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, PROJECT_ROOT


DEFAULT_OUTPUT_DIR = Path("data/lab03-filmnow/results/by_category")


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def condition_arg(value):
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "Use LABEL=EXPERIMENT, e.g. gpt55=lab03-filmnow/runs/gpt55/run1"
        )
    label, experiment = value.split("=", 1)
    label = label.strip()
    experiment = experiment.strip()
    if not label or not experiment:
        raise argparse.ArgumentTypeError("Both label and experiment are required.")
    return label, experiment


def count_json_files(path: Path):
    return len(list(path.glob("*.json"))) if path.exists() else 0


def artifact_path(path: Path):
    """Return stable, repo-relative paths for public benchmark metadata."""
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def validation_counts(paths: ExperimentPaths):
    validation = load_json(paths.results_analysis / "validation_report.json", {}) or {}
    summary = validation.get("summary", {})
    valid = summary.get("valid", validation.get("valid_reports"))
    missing = summary.get("missing", validation.get("missing_reports"))
    invalid = summary.get("invalid", validation.get("invalid_reports"))
    return valid, missing, invalid


def grade_summary(paths: ExperimentPaths):
    grade = load_json(paths.results_analysis / "grade_comparison.json", {}) or {}
    overall = grade.get("overall", {})
    scatter_points = overall.get("scatter_points", [])
    errors = [float(row["llm"]) - float(row["expert"]) for row in scatter_points]
    abs_errors = [abs(error) for error in errors]
    n = len(scatter_points)
    expert_mean = sum(float(row["expert"]) for row in scatter_points) / n if n else None
    llm_mean = sum(float(row["llm"]) for row in scatter_points) / n if n else None
    return {
        "grade_n": overall.get("n", n),
        "grade_mae": overall.get("mae"),
        "grade_rmse": overall.get("rmse"),
        "grade_bias": overall.get("mean_bias"),
        "grade_median_abs_error": statistics.median(abs_errors) if abs_errors else None,
        "grade_within_1": sum(1 for error in abs_errors if error <= 1.0) / n if n else None,
        "grade_within_2": sum(1 for error in abs_errors if error <= 2.0) / n if n else None,
        "expert_mean": expert_mean,
        "llm_mean": llm_mean,
        "scatter_points": scatter_points,
    }


def iter_problem_texts(eval_dir: Path):
    for path in sorted(eval_dir.glob("*.json")):
        payload = load_json(path, {}) or {}
        for criterion in payload.get("criteria", []):
            for deduction in criterion.get("deductions", []):
                problem = str(deduction.get("problem", "") or "").strip()
                if problem:
                    yield problem


def load_semantic_match_cache(paths: ExperimentPaths):
    """Merge available semantic matching caches for problem-level RQ2 metrics."""
    cache = {}
    cache_names = [
        "semantic_match_cache_flash.json.bak",
        "semantic_match_cache.bak.json",
        "semantic_match_cache.json",
    ]

    def completeness(match):
        return (
            len([p for p in match.get("matched_llm", []) if p])
            + len([p for p in match.get("unmatched_llm", []) if p])
            + len([p for p in match.get("unmatched_expert", match.get("unmatched_human", [])) if p])
        )

    for name in cache_names:
        payload = load_json(paths.results_analysis / name, {}) or {}
        if isinstance(payload, dict):
            for key, match in payload.items():
                if not isinstance(match, dict):
                    continue
                if key not in cache or completeness(match) >= completeness(cache[key]):
                    cache[key] = match
    return cache


def load_problem_index(eval_dir: Path):
    index: dict[str, dict[str, list[str]]] = defaultdict(dict)
    for path in sorted(eval_dir.glob("*.json")):
        payload = load_json(path, {}) or {}
        submission_id = payload.get("submission_id", path.stem)
        for criterion in payload.get("criteria", []):
            criterion_id = criterion.get("criterion_id")
            if not criterion_id:
                continue
            problems = [
                str(deduction.get("problem", "") or "").strip()
                for deduction in criterion.get("deductions", []) or []
            ]
            problems = [problem for problem in problems if problem]
            index[submission_id][criterion_id] = problems
    return index


def collect_unified_taxonomy(condition_paths: list[ExperimentPaths]):
    """Merge cached taxonomy labels so every condition uses the same problem-to-category map."""
    taxonomy: dict[str, set[str]] = defaultdict(set)
    for paths in condition_paths:
        payload = load_json(paths.results_analysis / "error_taxonomy.json", {}) or {}
        for problem, categories in payload.items():
            if isinstance(categories, list):
                taxonomy[problem].update(str(category) for category in categories if category)
            elif categories:
                taxonomy[problem].add(str(categories))

    for paths in condition_paths:
        for problem in iter_problem_texts(paths.results_gold_standard):
            taxonomy.setdefault(problem, {"other"})
        for problem in iter_problem_texts(paths.results_llm):
            taxonomy.setdefault(problem, {"other"})

    return {problem: sorted(categories or {"other"}) for problem, categories in taxonomy.items()}


def detection_summary(paths: ExperimentPaths, taxonomy: dict[str, list[str]], scatter_points: list[dict]):
    # Try to use error_overlap.json first (more reliable)
    error_overlap = load_json(paths.results_analysis / "error_overlap.json", {}) or {}
    if error_overlap.get("global_metrics"):
        return detection_summary_from_overlap(paths, taxonomy, scatter_points, error_overlap)
    
    # Fall back to semantic cache method
    expert = load_problem_index(paths.results_gold_standard)
    llm = load_problem_index(paths.results_llm)
    match_cache = load_semantic_match_cache(paths)

    totals = Counter()
    expected_by_category = Counter()
    detected_by_category = Counter()
    matched_reported_by_category = Counter()
    false_positive_by_category = Counter()
    false_negative_by_category = Counter()
    missing_match_keys = []
    submission_metrics = {}
    cache_omitted_reported_problems = 0
    cache_unrecognized_reported_problems = 0
    cache_unrecognized_reference_problems = 0

    def categories_for(problem):
        return taxonomy.get(problem) or ["other"]

    submissions = sorted(set(expert) | set(llm))
    for submission_id in submissions:
        submission_totals = Counter()
        criteria = sorted(set(expert.get(submission_id, {})) | set(llm.get(submission_id, {})))
        for criterion_id in criteria:
            expert_problems = expert.get(submission_id, {}).get(criterion_id, [])
            llm_problems = llm.get(submission_id, {}).get(criterion_id, [])

            totals["expected_reference_problems"] += len(expert_problems)
            totals["detected_problems"] += len(llm_problems)
            submission_totals["expected"] += len(expert_problems)
            submission_totals["llm_found"] += len(llm_problems)
            for problem in expert_problems:
                for category in categories_for(problem):
                    expected_by_category[category] += 1
            for problem in llm_problems:
                for category in categories_for(problem):
                    detected_by_category[category] += 1

            if expert_problems and llm_problems:
                cache_key = f"{submission_id}|{criterion_id}"
                match = match_cache.get(cache_key)
                if match:
                    # Handle both old and new cache formats
                    # New format: covered_expert, uncovered_expert, unmatched_llm
                    # Old format: matched_llm, unmatched_llm, unmatched_expert/unmatched_human
                    
                    covered_expert = match.get("covered_expert")
                    uncovered_expert = match.get("uncovered_expert")
                    unmatched_llm_list = match.get("unmatched_llm")
                    
                    # If new format exists, use it
                    if covered_expert is not None:
                        covered_expert = [p for p in (covered_expert or []) if p]
                        uncovered_expert = [p for p in (uncovered_expert or []) if p]
                        unmatched_llm_list = [p for p in (unmatched_llm_list or []) if p]
                        
                        # In new format:
                        # - covered_expert = expert problems that were matched by LLM
                        # - uncovered_expert = expert problems that were NOT matched
                        # - unmatched_llm = LLM problems that did NOT match any expert
                        # Therefore:
                        # - matched_llm = total LLM - unmatched_llm
                        # - covered_reference = len(covered_expert)
                        
                        matched_llm = [p for p in llm_problems if p not in unmatched_llm_list]
                        unmatched_llm = unmatched_llm_list
                        unmatched_expert = uncovered_expert
                        covered_reference = len(covered_expert)
                    else:
                        # Fall back to old format
                        remaining_llm = Counter(llm_problems)
                        matched_llm = []
                        unmatched_llm = []

                        for problem in [p for p in match.get("matched_llm", []) if p]:
                            if remaining_llm[problem] > 0:
                                matched_llm.append(problem)
                                remaining_llm[problem] -= 1
                            else:
                                cache_unrecognized_reported_problems += 1

                        for problem in [p for p in unmatched_llm_list if p]:
                            if remaining_llm[problem] > 0:
                                unmatched_llm.append(problem)
                                remaining_llm[problem] -= 1
                            else:
                                cache_unrecognized_reported_problems += 1

                        omitted_llm = list(remaining_llm.elements())
                        cache_omitted_reported_problems += len(omitted_llm)
                        unmatched_llm.extend(omitted_llm)

                        remaining_expert = Counter(expert_problems)
                        unmatched_expert = []
                        for problem in [p for p in match.get("unmatched_expert", match.get("unmatched_human", [])) if p]:
                            if remaining_expert[problem] > 0:
                                unmatched_expert.append(problem)
                                remaining_expert[problem] -= 1
                            else:
                                cache_unrecognized_reference_problems += 1

                        covered_reference = max(0, len(expert_problems) - len(unmatched_expert))

                    totals["matched_reported_problems"] += len(matched_llm)
                    totals["covered_reference_problems"] += covered_reference
                    totals["false_positive_problems"] += len(unmatched_llm)
                    totals["false_negative_problems"] += len(unmatched_expert)
                    submission_totals["intersection"] += covered_reference
                    submission_totals["additional"] += len(unmatched_llm)
                    submission_totals["missed"] += len(unmatched_expert)
                    for problem in matched_llm:
                        for category in categories_for(problem):
                            matched_reported_by_category[category] += 1
                    for problem in unmatched_llm:
                        for category in categories_for(problem):
                            false_positive_by_category[category] += 1
                    for problem in unmatched_expert:
                        for category in categories_for(problem):
                            false_negative_by_category[category] += 1
                else:
                    # Conservative fallback: no semantic evidence means no match.
                    missing_match_keys.append(cache_key)
                    totals["false_positive_problems"] += len(llm_problems)
                    totals["false_negative_problems"] += len(expert_problems)
                    submission_totals["additional"] += len(llm_problems)
                    submission_totals["missed"] += len(expert_problems)
                    for problem in llm_problems:
                        for category in categories_for(problem):
                            false_positive_by_category[category] += 1
                    for problem in expert_problems:
                        for category in categories_for(problem):
                            false_negative_by_category[category] += 1
            elif expert_problems:
                totals["false_negative_problems"] += len(expert_problems)
                submission_totals["missed"] += len(expert_problems)
                for problem in expert_problems:
                    for category in categories_for(problem):
                        false_negative_by_category[category] += 1
            elif llm_problems:
                totals["false_positive_problems"] += len(llm_problems)
                submission_totals["additional"] += len(llm_problems)
                for problem in llm_problems:
                    for category in categories_for(problem):
                        false_positive_by_category[category] += 1
        submission_metrics[submission_id] = {
            "expected": submission_totals["expected"],
            "llm_found": submission_totals["llm_found"],
            "intersection": submission_totals["intersection"],
            "additional": submission_totals["additional"],
            "missed": submission_totals["missed"],
        }

    precision = (
        totals["matched_reported_problems"] / totals["detected_problems"]
        if totals["detected_problems"]
        else 0
    )
    recall = (
        totals["covered_reference_problems"] / totals["expected_reference_problems"]
        if totals["expected_reference_problems"]
        else 0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0

    category_metrics = {}
    all_categories = sorted(set(expected_by_category) | set(detected_by_category))
    for category in all_categories:
        category_precision = (
            matched_reported_by_category[category] / detected_by_category[category]
            if detected_by_category[category]
            else 0
        )
        category_recall = (
            (expected_by_category[category] - false_negative_by_category[category])
            / expected_by_category[category]
            if expected_by_category[category]
            else 0
        )
        category_f1 = (
            2 * category_precision * category_recall / (category_precision + category_recall)
            if category_precision + category_recall
            else 0
        )
        category_metrics[category] = {
            "expected": expected_by_category[category],
            "detected": detected_by_category[category],
            "matched_reported": matched_reported_by_category[category],
            "FP": false_positive_by_category[category],
            "FN": false_negative_by_category[category],
            "precision": category_precision,
            "recall": category_recall,
            "f1": category_f1,
        }

    return {
        "expected_reference_problems": totals["expected_reference_problems"],
        "detected_problems": totals["detected_problems"],
        "matched_reported_problems": totals["matched_reported_problems"],
        "covered_reference_problems": totals["covered_reference_problems"],
        "false_positive_problems": totals["false_positive_problems"],
        "false_negative_problems": totals["false_negative_problems"],
        "overlap_precision": precision,
        "overlap_recall": recall,
        "overlap_f1": f1,
        "category_metrics": category_metrics,
        "submission_metrics": submission_metrics,
        "semantic_match_cache_entries": len(match_cache),
        "missing_semantic_match_keys": missing_match_keys,
        "missing_semantic_match_count": len(missing_match_keys),
        "cache_omitted_reported_problem_count": cache_omitted_reported_problems,
        "cache_unrecognized_reported_problem_count": cache_unrecognized_reported_problems,
        "cache_unrecognized_reference_problem_count": cache_unrecognized_reference_problems,
        "bias_correlation": compute_bias_correlation(paths, taxonomy, scatter_points)
    }

def detection_summary_from_overlap(paths: ExperimentPaths, taxonomy: dict[str, list[str]], scatter_points: list[dict], error_overlap: dict):
    """Build detection summary from error_overlap.json (more reliable than semantic cache)."""
    global_metrics = error_overlap.get("global_metrics", {})
    category_metrics_raw = error_overlap.get("category_metrics", {})
    
    # Convert category metrics to expected format
    category_metrics = {}
    for category, metrics in category_metrics_raw.items():
        tp = metrics.get("TP", 0)
        fp = metrics.get("FP", 0)
        fn = metrics.get("FN", 0)
        precision = metrics.get("Precision", 0)
        recall = metrics.get("Recall", 0)
        f1 = metrics.get("F1", 0)
        
        category_metrics[category] = {
            "expected": tp + fn,
            "detected": tp + fp,
            "matched_reported": tp,
            "FP": fp,
            "FN": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    
    # Calculate totals from global metrics
    total_expected = global_metrics.get("total_expected", 0)
    total_detected = global_metrics.get("total_llm_found", 0)
    intersection = global_metrics.get("intersection", 0)
    precision = global_metrics.get("precision", 0)
    recall = global_metrics.get("recall", 0)
    f1 = global_metrics.get("f1", 0)
    
    # Calculate FP and FN
    false_positives = total_detected - intersection
    false_negatives = total_expected - intersection
    
    # Compute bias correlation
    llm = load_problem_index(paths.results_llm)
    corr_data = []
    for point in scatter_points:
        sid = point["submission"]
        problems = llm.get(sid, {})
        total_problems = sum(len(p) for p in problems.values())
        diff = float(point["llm"]) - float(point["expert"])
        corr_data.append((total_problems, diff))
        
    if len(corr_data) >= 2:
        xs = [d[0] for d in corr_data]
        ys = [d[1] for d in corr_data]
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        den = (sum((x - mean_x)**2 for x in xs) * sum((y - mean_y)**2 for y in ys))**0.5
        r = num / den if den != 0 else 0
        bias_correlation = {"pearson_r": r, "r_squared": r**2}
    else:
        bias_correlation = {"pearson_r": 0, "r_squared": 0}
    
    return {
        "expected_reference_problems": total_expected,
        "detected_problems": total_detected,
        "matched_reported_problems": intersection,
        "covered_reference_problems": intersection,
        "false_positive_problems": false_positives,
        "false_negative_problems": false_negatives,
        "overlap_precision": precision,
        "overlap_recall": recall,
        "overlap_f1": f1,
        "category_metrics": category_metrics,
        "submission_metrics": error_overlap.get("submission_metrics", {}),
        "semantic_match_cache_entries": 0,  # Not applicable for overlap method
        "missing_semantic_match_keys": [],
        "missing_semantic_match_count": 0,
        "cache_omitted_reported_problem_count": 0,
        "cache_unrecognized_reported_problem_count": 0,
        "cache_unrecognized_reference_problem_count": 0,
        "bias_correlation": bias_correlation
    }


def compute_bias_correlation(paths, taxonomy, scatter_points):
    llm = load_problem_index(paths.results_llm)
    
    corr_data = []
    for point in scatter_points:
        sid = point["submission"]
        problems = llm.get(sid, {})
        total_problems = sum(len(p) for p in problems.values())
        diff = float(point["llm"]) - float(point["expert"])
        corr_data.append((total_problems, diff))
        
    if len(corr_data) < 2:
        return {"pearson_r": 0, "r_squared": 0}
        
    xs = [d[0] for d in corr_data]
    ys = [d[1] for d in corr_data]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = (sum((x - mean_x)**2 for x in xs) * sum((y - mean_y)**2 for y in ys))**0.5
    
    r = num / den if den != 0 else 0
    return {"pearson_r": r, "r_squared": r**2}


def summarize_condition(label: str, experiment: str, taxonomy: dict[str, list[str]]):
    paths = ExperimentPaths(experiment)
    config = load_json(paths.experiment_config, {}) or {}
    llm_protocol = config.get("llm_protocol", {})
    valid, missing, invalid = validation_counts(paths)
    grade = grade_summary(paths)
    detection = detection_summary(paths, taxonomy, grade.get("scatter_points", []))

    summary = {
        "label": label,
        "experiment": experiment,
        "provider": llm_protocol.get("provider"),
        "model": llm_protocol.get("model"),
        "temperature": llm_protocol.get("temperature"),
        "reasoning_effort": llm_protocol.get("reasoning_effort"),
        "prompt_version": llm_protocol.get("prompt_version"),
        "llm_output_count": count_json_files(paths.results_llm),
        "validation_valid": valid,
        "validation_missing": missing,
        "validation_invalid": invalid,
        "paths": {
            "experiment_config": artifact_path(paths.experiment_config),
            "grade_comparison": artifact_path(paths.results_analysis / "grade_comparison.json"),
            "error_taxonomy": artifact_path(paths.results_analysis / "error_taxonomy.json"),
        },
    }
    summary.update({key: value for key, value in grade.items() if key != "scatter_points"})
    summary.update({key: value for key, value in detection.items() if key not in ("category_metrics", "bias_correlation")})
    summary["category_metrics"] = detection["category_metrics"]
    summary["bias_correlation"] = detection["bias_correlation"]
    return summary


def assert_common_reference(summaries):
    expected_values = {summary["expected_reference_problems"] for summary in summaries}
    if len(expected_values) != 1:
        raise RuntimeError(
            "Problem-level benchmark failed: expected_reference_problems differs across conditions: "
            + ", ".join(f"{summary['label']}={summary['expected_reference_problems']}" for summary in summaries)
        )


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def format_float(value, digits=4):
    if value is None:
        return ""
    return f"{float(value):.{digits}f}"


def format_pvalue(value):
    if value is None:
        return ""
    return f"{float(value):.3e}"


def exact_sign_test_pvalue(left_higher: int, right_higher: int):
    n = left_higher + right_higher
    if n == 0:
        return None
    tail = min(left_higher, right_higher)
    probability = 2 * sum(math.comb(n, k) for k in range(tail + 1)) / (2 ** n)
    return min(1.0, probability)


def submission_metric_value(metric_payload: dict, metric: str):
    expected = metric_payload.get("expected", 0) or 0
    reported = metric_payload.get("llm_found", 0) or 0
    matched = metric_payload.get("intersection", 0) or 0
    if metric == "recall":
        return matched / expected if expected else None
    if metric == "precision":
        return matched / reported if reported else None
    raise ValueError(f"Unsupported metric for statistical test: {metric}")


def build_submission_level_sign_tests(summaries: list[dict]):
    tests = []
    submission_rows = []

    for left_index in range(len(summaries)):
        for right_index in range(left_index + 1, len(summaries)):
            left = summaries[left_index]
            right = summaries[right_index]
            left_metrics = left.get("submission_metrics", {}) or {}
            right_metrics = right.get("submission_metrics", {}) or {}
            submission_ids = sorted(set(left_metrics) & set(right_metrics))

            for metric in ("recall", "precision"):
                left_higher = 0
                right_higher = 0
                ties = 0
                omitted = 0
                differences = []

                for submission_id in submission_ids:
                    left_value = submission_metric_value(left_metrics[submission_id], metric)
                    right_value = submission_metric_value(right_metrics[submission_id], metric)
                    row = {
                        "metric": metric,
                        "left_label": left["label"],
                        "right_label": right["label"],
                        "submission_id": submission_id,
                        "left_value": left_value,
                        "right_value": right_value,
                        "difference_left_minus_right": None,
                        "outcome": None,
                        "included_in_test": False,
                        "omit_reason": "",
                    }

                    if left_value is None or right_value is None:
                        omitted += 1
                        row["outcome"] = "omitted"
                        row["omit_reason"] = f"{metric}_undefined"
                        submission_rows.append(row)
                        continue

                    difference = left_value - right_value
                    row["difference_left_minus_right"] = difference
                    row["included_in_test"] = True
                    differences.append(difference)

                    if abs(difference) <= 1e-12:
                        ties += 1
                        row["outcome"] = "tie"
                    elif difference > 0:
                        left_higher += 1
                        row["outcome"] = left["label"]
                    else:
                        right_higher += 1
                        row["outcome"] = right["label"]
                    submission_rows.append(row)

                non_tied = left_higher + right_higher
                tests.append(
                    {
                        "test": "two_sided_exact_sign_test",
                        "metric": metric,
                        "unit": "submission",
                        "left_label": left["label"],
                        "right_label": right["label"],
                        "left_model": left.get("model"),
                        "right_model": right.get("model"),
                        "n_common_submissions": len(submission_ids),
                        "n_compared": len(submission_ids) - omitted,
                        "n_used_in_binomial_test": non_tied,
                        "left_higher": left_higher,
                        "right_higher": right_higher,
                        "ties": ties,
                        "omitted": omitted,
                        "p_value_two_sided": exact_sign_test_pvalue(left_higher, right_higher),
                        "mean_left": statistics.mean(
                            row["left_value"]
                            for row in submission_rows
                            if row["metric"] == metric
                            and row["left_label"] == left["label"]
                            and row["right_label"] == right["label"]
                            and row["included_in_test"]
                        )
                        if len(submission_ids) > omitted
                        else None,
                        "mean_right": statistics.mean(
                            row["right_value"]
                            for row in submission_rows
                            if row["metric"] == metric
                            and row["left_label"] == left["label"]
                            and row["right_label"] == right["label"]
                            and row["included_in_test"]
                        )
                        if len(submission_ids) > omitted
                        else None,
                        "median_difference_left_minus_right": statistics.median(differences)
                        if differences
                        else None,
                        "notes": (
                            "Ties are reported descriptively and omitted from the exact binomial calculation. "
                            "Rows with undefined precision or recall are omitted from the test."
                        ),
                    }
                )

    return {
        "method": (
            "For each common submission, precision and recall are computed separately for each model. "
            "A two-sided exact sign test checks whether one model has the higher paired value more often "
            "than expected by chance. The submission is the paired unit."
        ),
        "tests": tests,
        "submission_rows": submission_rows,
    }


def write_outputs(output_dir: Path, summaries: list[dict], taxonomy: dict[str, list[str]]):
    output_dir.mkdir(parents=True, exist_ok=True)
    assert_common_reference(summaries)
    statistical_tests = build_submission_level_sign_tests(summaries)

    payload = {
        "benchmark_method": (
            "RQ1 uses each experiment's grade_comparison.json. RQ2 is recomputed at "
            "problem level from semantic_match_cache entries. When multiple cache files contain "
            "the same submission/criterion key, the most complete entry is used. The unified "
            "taxonomy is used only for category breakdowns, not to decide whether a model "
            "identified the same problem."
        ),
        "unified_taxonomy_problem_count": len(taxonomy),
        "conditions": summaries,
        "statistical_tests": statistical_tests["tests"],
    }
    write_json(output_dir / "model_benchmark.json", payload)
    write_json(output_dir / "model_statistical_tests.json", statistical_tests)

    summary_fields = [
        "label",
        "experiment",
        "provider",
        "model",
        "temperature",
        "reasoning_effort",
        "prompt_version",
        "llm_output_count",
        "validation_valid",
        "validation_missing",
        "validation_invalid",
        "grade_n",
        "grade_mae",
        "grade_rmse",
        "grade_bias",
        "grade_median_abs_error",
        "grade_within_1",
        "grade_within_2",
        "expert_mean",
        "llm_mean",
        "expected_reference_problems",
        "detected_problems",
        "matched_reported_problems",
        "covered_reference_problems",
        "false_positive_problems",
        "false_negative_problems",
        "overlap_precision",
        "overlap_recall",
        "overlap_f1",
        "semantic_match_cache_entries",
        "missing_semantic_match_count",
        "cache_omitted_reported_problem_count",
        "cache_unrecognized_reported_problem_count",
        "cache_unrecognized_reference_problem_count",
    ]
    write_csv(
        output_dir / "model_benchmark.csv",
        [{field: summary.get(field) for field in summary_fields} for summary in summaries],
        summary_fields,
    )

    category_rows = []
    all_categories = sorted({category for summary in summaries for category in summary["category_metrics"]})
    for summary in summaries:
        for category in all_categories:
            metric = summary["category_metrics"].get(category, {})
            category_rows.append(
                {
                    "label": summary["label"],
                    "model": summary["model"],
                    "category": category,
                    "expected": metric.get("expected", 0),
                    "detected": metric.get("detected", 0),
                    "matched_reported": metric.get("matched_reported", 0),
                    "FP": metric.get("FP", 0),
                    "FN": metric.get("FN", 0),
                    "precision": metric.get("precision", 0),
                    "recall": metric.get("recall", 0),
                    "f1": metric.get("f1", 0),
                }
            )
    write_csv(
        output_dir / "model_benchmark_by_category.csv",
        category_rows,
        ["label", "model", "category", "expected", "detected", "matched_reported", "FP", "FN", "precision", "recall", "f1"],
    )

    statistical_test_fields = [
        "test",
        "metric",
        "unit",
        "left_label",
        "right_label",
        "left_model",
        "right_model",
        "n_common_submissions",
        "n_compared",
        "n_used_in_binomial_test",
        "left_higher",
        "right_higher",
        "ties",
        "omitted",
        "p_value_two_sided",
        "mean_left",
        "mean_right",
        "median_difference_left_minus_right",
        "notes",
    ]
    write_csv(
        output_dir / "model_statistical_tests.csv",
        [{field: test.get(field) for field in statistical_test_fields} for test in statistical_tests["tests"]],
        statistical_test_fields,
    )

    statistical_row_fields = [
        "metric",
        "left_label",
        "right_label",
        "submission_id",
        "left_value",
        "right_value",
        "difference_left_minus_right",
        "outcome",
        "included_in_test",
        "omit_reason",
    ]
    write_csv(
        output_dir / "model_statistical_tests_by_submission.csv",
        [
            {field: row.get(field) for field in statistical_row_fields}
            for row in statistical_tests["submission_rows"]
        ],
        statistical_row_fields,
    )

    md_lines = [
        "# Model Benchmark",
        "",
        "RQ2 is recomputed at problem level from semantic matching caches. When multiple cache files contain the same submission/criterion key, the most complete entry is used. The unified taxonomy is used only for category breakdowns.",
        "",
        "## RQ1: Grade Concordance",
        "",
        "| condition | model | outputs | MAE | RMSE | bias | median abs. error | within ±1 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in summaries:
        md_lines.append(
            "| {label} | {model} | {outputs} | {mae} | {rmse} | {bias} | {median} | {within} |".format(
                label=summary["label"],
                model=summary.get("model") or "",
                outputs=summary.get("llm_output_count") or 0,
                mae=format_float(summary.get("grade_mae")),
                rmse=format_float(summary.get("grade_rmse")),
                bias=format_float(summary.get("grade_bias")),
                median=format_float(summary.get("grade_median_abs_error")),
                within=f"{float(summary.get('grade_within_1') or 0):.1%}",
            )
        )
    md_lines.extend(
        [
            "",
            "## RQ2: Problem-Level Detection",
            "",
            "| condition | model | expected problems | reported problems | matched reported | covered reference | FP | FN | precision | recall | F1 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for summary in summaries:
        md_lines.append(
            "| {label} | {model} | {expected} | {detected} | {matched} | {covered} | {fp} | {fn} | {precision} | {recall} | {f1} |".format(
                label=summary["label"],
                model=summary.get("model") or "",
                expected=summary["expected_reference_problems"],
                detected=summary["detected_problems"],
                matched=summary["matched_reported_problems"],
                covered=summary["covered_reference_problems"],
                fp=summary["false_positive_problems"],
                fn=summary["false_negative_problems"],
                precision=format_float(summary.get("overlap_precision")),
                recall=format_float(summary.get("overlap_recall")),
                f1=format_float(summary.get("overlap_f1")),
            )
        )
    md_lines.extend(
        [
            "",
            "## RQ2: Paired Submission-Level Statistical Tests",
            "",
            "Two-sided exact sign tests compare per-submission precision and recall between model conditions. Ties are reported but omitted from the exact binomial calculation.",
            "",
            "| metric | comparison | compared submissions | left higher | right higher | ties | omitted | two-sided p-value |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for test in statistical_tests["tests"]:
        md_lines.append(
            "| {metric} | {left} vs {right} | {compared} | {left_higher} | {right_higher} | {ties} | {omitted} | {pvalue} |".format(
                metric=test["metric"],
                left=test["left_label"],
                right=test["right_label"],
                compared=test["n_compared"],
                left_higher=test["left_higher"],
                right_higher=test["right_higher"],
                ties=test["ties"],
                omitted=test["omitted"],
                pvalue=format_pvalue(test["p_value_two_sided"]),
            )
        )
    (output_dir / "model_benchmark.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"Benchmark JSON: {output_dir / 'model_benchmark.json'}")
    print(f"Benchmark CSV: {output_dir / 'model_benchmark.csv'}")
    print(f"Benchmark category CSV: {output_dir / 'model_benchmark_by_category.csv'}")
    print(f"Benchmark statistical tests JSON: {output_dir / 'model_statistical_tests.json'}")
    print(f"Benchmark statistical tests CSV: {output_dir / 'model_statistical_tests.csv'}")
    print(f"Benchmark statistical tests by submission CSV: {output_dir / 'model_statistical_tests_by_submission.csv'}")
    print(f"Benchmark Markdown: {output_dir / 'model_benchmark.md'}")
    
    print("\n--- Bias Correlation Analysis ---")
    for s in summaries:
        corr = s.get("bias_correlation", {})
        print(f"Condition: {s['label']}")
        print(f"  Pearson R: {corr.get('pearson_r'):.4f}")
        print(f"  R²: {corr.get('r_squared'):.4f}")


def parse_args():
    parser = argparse.ArgumentParser(description="Build a cross-model benchmark from completed experiments.")
    parser.add_argument(
        "--condition",
        action="append",
        type=condition_arg,
        required=True,
        help="Condition in LABEL=EXPERIMENT format. Can be repeated.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main():
    args = parse_args()
    condition_paths = [ExperimentPaths(experiment) for _, experiment in args.condition]
    taxonomy = collect_unified_taxonomy(condition_paths)
    summaries = [summarize_condition(label, experiment, taxonomy) for label, experiment in args.condition]
    write_outputs(args.output_dir, summaries, taxonomy)


if __name__ == "__main__":
    main()
