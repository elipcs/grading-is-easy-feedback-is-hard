#!/usr/bin/env python3
"""Aggregate three-run repeated-measures analyses for the paper (RQ1, RQ2, stability)."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, PROJECT_ROOT
from pipeline.utils.determinism import (
    extract_grade_vector,
    load_json,
    load_llm_outputs,
    pairwise_grade_metrics,
    write_json,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "data/lab03-filmnow/results/benchmark"

STUDIES = {
    "gemini": {
        "label": "Gemini 3.1 Pro Preview",
        "manifest": "data/lab03-filmnow/study/gemini31pro.json",
    },
    "gpt": {
        "label": "GPT-5.5",
        "manifest": "data/lab03-filmnow/study/gpt55.json",
    },
}

BASELINE_EXPERIMENT = "lab03-filmnow/runs/gemini31pro/run1"


def load_total_scores(experiment: str, evaluator: str) -> dict[str, float]:
    paths = ExperimentPaths(experiment)
    if evaluator == "expert":
        directory = paths.results_gold_standard
    elif evaluator == "human":
        directory = paths.results_human
    else:
        directory = paths.results_llm
    scores = {}
    if not directory.exists():
        return scores
    for path in sorted(directory.glob("S*.json")):
        payload = load_json(path, {}) or {}
        scores[path.stem] = float(payload.get("total_score", 0.0))
    return scores


def grade_metrics(expert: dict[str, float], predicted: dict[str, float]) -> dict:
    shared = sorted(set(expert) & set(predicted))
    if not shared:
        return {"n": 0}
    errors = [predicted[s] - expert[s] for s in shared]
    abs_errors = [abs(error) for error in errors]
    n = len(shared)
    return {
        "n": n,
        "mean_grade": statistics.mean(predicted[s] for s in shared),
        "mae": statistics.mean(abs_errors),
        "rmse": math.sqrt(statistics.mean(error * error for error in errors)),
        "bias": statistics.mean(errors),
        "median_abs_error": statistics.median(abs_errors),
        "within_1": sum(1 for error in abs_errors if error <= 1.0) / n,
        "within_2": sum(1 for error in abs_errors if error <= 2.0) / n,
        "expert_mean": statistics.mean(expert[s] for s in shared),
    }


def submission_run_abs_errors(
    expert: dict[str, float],
    runs: list[dict[str, float]],
) -> dict[str, list[float]]:
    shared = sorted(set(expert) & set.intersection(*(set(run) for run in runs)))
    return {
        submission_id: [abs(run[submission_id] - expert[submission_id]) for run in runs]
        for submission_id in shared
    }


def primary_run_averaged_mae(submission_errors: dict[str, list[float]]) -> float:
    if not submission_errors:
        return float("nan")
    per_submission = [statistics.mean(errors) for errors in submission_errors.values()]
    return statistics.mean(per_submission)


def repeated_observation_rmse(submission_errors: dict[str, list[float]]) -> float:
    """Conventional RMSE over all repeated run-level errors.

    Each submission contributes all of its run-level squared errors to the
    point estimate. Cluster bootstrap resampling still occurs by submission.
    """
    squared_errors = [
        error * error
        for errors in submission_errors.values()
        for error in errors
    ]
    return (
        math.sqrt(statistics.mean(squared_errors))
        if squared_errors
        else float("nan")
    )


def metric_from_submission_errors(
    submission_errors: dict[str, list[float]],
    reducer,
) -> float:
    if not submission_errors:
        return float("nan")
    per_submission = [reducer(errors) for errors in submission_errors.values()]
    return statistics.mean(per_submission)


def bootstrap_ci(
    submission_errors: dict[str, list[float]],
    metric_fn,
    n_boot: int = 5000,
    seed: int = 20260713,
) -> tuple[float, float, float]:
    ids = sorted(submission_errors)
    if not ids:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    estimates = []
    for _ in range(n_boot):
        sample = [rng.choice(ids) for _ in range(len(ids))]
        # Preserve repeated draws. Using submission_id as the key would collapse
        # duplicates and no longer represent a bootstrap sample of size n.
        sampled = {
            f"{draw_index}:{submission_id}": submission_errors[submission_id]
            for draw_index, submission_id in enumerate(sample)
        }
        estimates.append(metric_fn(sampled))
    estimates.sort()
    point = metric_fn(submission_errors)
    lower = estimates[int(0.025 * len(estimates))]
    upper = estimates[int(0.975 * len(estimates)) - 1]
    return point, lower, upper


def bootstrap_mean_ci(
    values: list[float],
    n_boot: int = 5000,
    seed: int = 20260713,
) -> tuple[float, float, float]:
    if not values:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    estimates = [
        statistics.mean(rng.choice(values) for _ in range(len(values)))
        for _ in range(n_boot)
    ]
    estimates.sort()
    return (
        statistics.mean(values),
        estimates[int(0.025 * len(estimates))],
        estimates[int(0.975 * len(estimates)) - 1],
    )


def bootstrap_detection_ci(
    run_detection: list[dict],
    metric: str,
    n_boot: int = 5000,
    seed: int = 20260713,
) -> tuple[float, float, float]:
    shared = sorted(
        set.intersection(*(set(run["submission_metrics"]) for run in run_detection))
    )
    if not shared:
        return float("nan"), float("nan"), float("nan")

    def estimate(sample: list[str]) -> float:
        run_values = []
        for run in run_detection:
            rows = run["submission_metrics"]
            tp = sum(rows[sid]["tp"] for sid in sample)
            fp = sum(rows[sid]["fp"] for sid in sample)
            fn = sum(rows[sid]["fn"] for sid in sample)
            denominator = tp + fp if metric == "precision" else tp + fn
            run_values.append(tp / denominator if denominator else float("nan"))
        return statistics.mean(value for value in run_values if not math.isnan(value))

    rng = random.Random(seed)
    estimates = [
        estimate([rng.choice(shared) for _ in range(len(shared))])
        for _ in range(n_boot)
    ]
    estimates.sort()
    return (
        estimate(shared),
        estimates[int(0.025 * len(estimates))],
        estimates[int(0.975 * len(estimates)) - 1],
    )


def wilcoxon_pvalue(differences: list[float]) -> float:
    nonzero = [(index + 1, abs(diff)) for index, diff in enumerate(differences) if diff != 0]
    if not nonzero:
        return 1.0
    ranks = _rankdata([abs_diff for _, abs_diff in nonzero])
    w_plus = sum(rank for (index, _), rank in zip(nonzero, ranks) if differences[index - 1] > 0)
    n = len(nonzero)
    # Normal approximation for two-sided test
    mean_w = n * (n + 1) / 4
    var_w = n * (n + 1) * (2 * n + 1) / 24
    if var_w == 0:
        return 1.0
    z = abs(w_plus - mean_w) / math.sqrt(var_w)
    return math.erfc(z / math.sqrt(2))


def _rankdata(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(values):
        start = index
        value = values[order[index]]
        while index < len(values) and values[order[index]] == value:
            index += 1
        avg_rank = (start + index + 2) / 2
        for position in range(start, index):
            ranks[order[position]] = avg_rank
    return ranks


def friedman_test(*groups: list[float]) -> tuple[float, float]:
    data = np.array(groups, dtype=float).T
    n, k = data.shape
    ranks = np.zeros_like(data)
    for row in range(n):
        order = np.argsort(data[row])
        row_ranks = np.zeros(k)
        sorted_vals = data[row, order]
        rank = 1
        idx = 0
        while idx < k:
            start = idx
            while idx < k and sorted_vals[idx] == sorted_vals[start]:
                idx += 1
            avg_rank = (start + idx + 1) / 2
            for position in range(start, idx):
                row_ranks[order[position]] = avg_rank
        ranks[row] = row_ranks
    rank_sums = ranks.sum(axis=0)
    chi2 = (12 / (n * k * (k + 1))) * np.sum(rank_sums**2) - 3 * n * (k + 1)
    # chi-square survival with k-1 df via Wilson-Hilferty approx is overkill; use scipy-free approx
  # For paper, use chi2 CDF approximation with incomplete gamma - simple series:
    p_value = _chi2_sf(chi2, k - 1)
    return float(chi2), float(p_value)


def _chi2_sf(x: float, df: int) -> float:
    if x <= 0:
        return 1.0
    # Wilson-Hilferty approximation to chi-square upper tail
    z = ((x / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    return 0.5 * math.erfc(z / math.sqrt(2))


def holm_adjust(p_values: list[tuple[str, float]]) -> list[dict]:
    ordered = sorted(p_values, key=lambda item: item[1])
    m = len(ordered)
    adjusted = []
    running_max = 0.0
    for index, (name, p_value) in enumerate(ordered, start=1):
        adj = min(1.0, (m - index + 1) * p_value)
        running_max = max(running_max, adj)
        adjusted.append({"contrast": name, "p_raw": p_value, "p_holm": running_max})
    return adjusted


def paired_permutation_pvalue(differences: list[float], n_perm: int = 20000, seed: int = 7) -> float:
    if not differences:
        return float("nan")
    observed = abs(statistics.mean(differences))
    rng = random.Random(seed)
    count = 0
    for _ in range(n_perm):
        flipped = [diff if rng.random() < 0.5 else -diff for diff in differences]
        if abs(statistics.mean(flipped)) >= observed:
            count += 1
    return (count + 1) / (n_perm + 1)


def icc_2_1(matrix: np.ndarray) -> float:
    data = np.asarray(matrix, dtype=float)
    n, k = data.shape
    if n < 2 or k < 2:
        return float("nan")
    mean_row = data.mean(axis=1)
    mean_col = data.mean(axis=0)
    grand_mean = data.mean()
    ssr = k * np.sum((mean_row - grand_mean) ** 2)
    ssc = n * np.sum((mean_col - grand_mean) ** 2)
    sst = np.sum((data - grand_mean) ** 2)
    sse = sst - ssr - ssc
    msr = ssr / (n - 1)
    msc = ssc / (k - 1)
    mse = sse / ((n - 1) * (k - 1))
    denom = msr + (k - 1) * mse + k * (msc - mse) / n
    if denom == 0:
        return float("nan")
    return float((msr - mse) / denom)


def bootstrap_icc_ci(matrix: np.ndarray, n_boot: int = 5000, seed: int = 13) -> tuple[float, float, float]:
    n = matrix.shape[0]
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        estimates.append(icc_2_1(matrix[idx]))
    estimates = sorted(estimates)
    point = icc_2_1(matrix)
    return point, estimates[int(0.025 * len(estimates))], estimates[int(0.975 * len(estimates)) - 1]


def agreement_rates(grade_matrix: dict[str, list[float]]) -> dict:
    submissions = sorted(grade_matrix)
    if not submissions:
        return {}
    exact = 0
    within_05 = 0
    within_1 = 0
    for submission_id in submissions:
        values = grade_matrix[submission_id]
        spread = max(values) - min(values)
        if spread == 0:
            exact += 1
        if spread <= 0.5:
            within_05 += 1
        if spread <= 1.0:
            within_1 += 1
    n = len(submissions)
    return {
        "exact_all_runs": exact / n,
        "within_0_5": within_05 / n,
        "within_1_0": within_1 / n,
    }


def load_overlap(experiment: str) -> dict:
    paths = ExperimentPaths(experiment)
    return load_json(paths.results_analysis / "error_overlap.json", {}) or {}


def submission_detection_metrics(overlap: dict) -> dict[str, dict]:
    rows = {}
    for submission_id, metrics in (overlap.get("submission_metrics") or {}).items():
        expected = metrics.get("expected", 0) or 0
        reported = metrics.get("llm_found", 0) or 0
        matched = metrics.get("intersection", 0) or 0
        precision = matched / reported if reported else None
        recall = matched / expected if expected else None
        f1 = None
        if precision is not None and recall is not None and (precision + recall) > 0:
            f1 = 2 * precision * recall / (precision + recall)
        rows[submission_id] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "tp": matched,
            "fp": metrics.get("additional", 0) or 0,
            "fn": metrics.get("missed", 0) or 0,
        }
    return rows


def exact_sign_test(left_higher: int, right_higher: int) -> float | None:
    n = left_higher + right_higher
    if n == 0:
        return None
    tail = min(left_higher, right_higher)
    probability = 2 * sum(math.comb(n, k) for k in range(tail + 1)) / (2 ** n)
    return min(1.0, probability)


def compare_submission_metrics(left: dict[str, dict], right: dict[str, dict], metric: str) -> dict:
    left_higher = right_higher = ties = omitted = 0
    for submission_id in sorted(set(left) & set(right)):
        left_value = left[submission_id].get(metric)
        right_value = right[submission_id].get(metric)
        if left_value is None or right_value is None:
            omitted += 1
            continue
        if left_value > right_value:
            left_higher += 1
        elif right_value > left_value:
            right_higher += 1
        else:
            ties += 1
    return {
        "metric": metric,
        "left_higher": left_higher,
        "right_higher": right_higher,
        "ties": ties,
        "omitted": omitted,
        "p_value_two_sided": exact_sign_test(left_higher, right_higher),
    }


def run_labels_from_manifest(manifest: dict) -> list[tuple[str, str]]:
    runs = [("run1", manifest["baseline_experiment"])]
    for index, experiment in enumerate(manifest["repeat_experiments"], start=2):
        runs.append((f"run{index}", experiment))
    return runs


def analyze_model(study_key: str, manifest: dict, expert: dict[str, float]) -> dict:
    run_entries = run_labels_from_manifest(manifest)
    run_scores = []
    run_grade_summaries = []
    run_detection = []
    for label, experiment in run_entries:
        scores = load_total_scores(experiment, "llm")
        run_scores.append(scores)
        run_grade_summaries.append(
            {
                "label": label,
                "experiment": experiment,
                **grade_metrics(expert, scores),
            }
        )
        overlap = load_overlap(experiment)
        global_metrics = overlap.get("global_metrics", {})
        run_detection.append(
            {
                "label": label,
                "experiment": experiment,
                "precision": global_metrics.get("precision"),
                "recall": global_metrics.get("recall"),
                "f1": global_metrics.get("f1"),
                "tp": global_metrics.get("intersection"),
                "fp": (global_metrics.get("total_llm_found", 0) or 0) - (global_metrics.get("intersection", 0) or 0),
                "fn": (global_metrics.get("total_expected", 0) or 0) - (global_metrics.get("intersection", 0) or 0),
                "submission_metrics": submission_detection_metrics(overlap),
            }
        )

    submission_errors = submission_run_abs_errors(expert, run_scores)
    shared = sorted(submission_errors)
    signed = [statistics.mean([run[s] - expert[s] for run in run_scores]) for s in shared]
    primary = {
        "mae": primary_run_averaged_mae(submission_errors),
        "rmse": repeated_observation_rmse(submission_errors),
        "bias": statistics.mean(signed) if signed else float("nan"),
        "within_1": metric_from_submission_errors(
            submission_errors,
            lambda errors: sum(1 for error in errors if error <= 1.0) / len(errors),
        ),
        "mean_grade": statistics.mean(
            statistics.mean([run[s] for run in run_scores]) for s in shared
        )
        if shared
        else float("nan"),
    }

    mae_ci = bootstrap_ci(submission_errors, primary_run_averaged_mae)
    rmse_ci = bootstrap_ci(submission_errors, repeated_observation_rmse)

    detection_shared = sorted(
        set.intersection(*(set(run["submission_metrics"]) for run in run_detection))
    )
    submission_avg_detection = {}
    for submission_id in detection_shared:
        precisions = [
            run_detection[index]["submission_metrics"][submission_id]["precision"]
            for index in range(3)
            if run_detection[index]["submission_metrics"][submission_id]["precision"] is not None
        ]
        recalls = [
            run_detection[index]["submission_metrics"][submission_id]["recall"]
            for index in range(3)
            if run_detection[index]["submission_metrics"][submission_id]["recall"] is not None
        ]
        if not precisions or not recalls:
            continue
        submission_avg_detection[submission_id] = {
            "precision": statistics.mean(precisions),
            "recall": statistics.mean(recalls),
        }

    def mean_precision(rows: dict[str, dict]) -> float:
        values = [row["precision"] for row in rows.values() if row.get("precision") is not None]
        return statistics.mean(values) if values else float("nan")

    def mean_recall(rows: dict[str, dict]) -> float:
        values = [row["recall"] for row in rows.values() if row.get("recall") is not None]
        return statistics.mean(values) if values else float("nan")

    precision_ci = bootstrap_detection_ci(run_detection, "precision")
    recall_ci = bootstrap_detection_ci(run_detection, "recall")

    run_metric_ranges = {
        "mae": {
            "mean_of_runs": statistics.mean(row["mae"] for row in run_grade_summaries),
            "min": min(row["mae"] for row in run_grade_summaries),
            "max": max(row["mae"] for row in run_grade_summaries),
        },
        "precision": {
            "mean_of_runs": statistics.mean(row["precision"] for row in run_detection if row["precision"] is not None),
            "min": min(row["precision"] for row in run_detection),
            "max": max(row["precision"] for row in run_detection),
        },
        "recall": {
            "mean_of_runs": statistics.mean(row["recall"] for row in run_detection if row["recall"] is not None),
            "min": min(row["recall"] for row in run_detection),
            "max": max(row["recall"] for row in run_detection),
        },
    }

    # Stability
    shared_submissions = sorted(set.intersection(*(set(run) for run in run_scores)))
    grade_matrix = {
        submission_id: [run_scores[index][submission_id] for index in range(3)]
        for submission_id in shared_submissions
    }
    matrix = np.array([grade_matrix[submission_id] for submission_id in shared_submissions])
    icc_point, icc_lo, icc_hi = bootstrap_icc_ci(matrix)

    pairwise = []
    outputs = [load_llm_outputs(experiment) for _, experiment in run_entries]
    for left_index, right_index in combinations(range(3), 2):
        pairwise.append(
            {
                "comparison": f"{run_entries[left_index][0]}_vs_{run_entries[right_index][0]}",
                **pairwise_grade_metrics(outputs[left_index], outputs[right_index]),
            }
        )

    return {
        "study": study_key,
        "label": STUDIES[study_key]["label"],
        "runs": run_grade_summaries,
        "primary_grade_concordance": {
            **primary,
            "mae_ci95": {"point": mae_ci[0], "lower": mae_ci[1], "upper": mae_ci[2]},
            "rmse_ci95": {"point": rmse_ci[0], "lower": rmse_ci[1], "upper": rmse_ci[2]},
        },
        "run_metric_ranges": run_metric_ranges,
        "detection_by_run": run_detection,
        "detection_primary": {
            "precision_mean_of_run_means": run_metric_ranges["precision"]["mean_of_runs"],
            "recall_mean_of_run_means": run_metric_ranges["recall"]["mean_of_runs"],
            "precision_ci95": {"point": precision_ci[0], "lower": precision_ci[1], "upper": precision_ci[2]},
            "recall_ci95": {"point": recall_ci[0], "lower": recall_ci[1], "upper": recall_ci[2]},
        },
        "stability": {
            "icc_2_1": icc_point,
            "icc_2_1_ci95": {"lower": icc_lo, "upper": icc_hi},
            "agreement": agreement_rates(grade_matrix),
            "pairwise_run_metrics": pairwise,
        },
        "submission_run_avg_mae": {
            submission_id: statistics.mean(submission_errors[submission_id])
            for submission_id in submission_errors
        },
        "submission_run_avg_detection": submission_avg_detection,
    }


def compare_models(gemini: dict, gpt: dict) -> dict:
    shared = sorted(set(gemini["submission_run_avg_mae"]) & set(gpt["submission_run_avg_mae"]))
    mae_diffs = [gpt["submission_run_avg_mae"][s] - gemini["submission_run_avg_mae"][s] for s in shared]
    mae_diff_ci = bootstrap_mean_ci(mae_diffs)
    try:
        wilcoxon_p = wilcoxon_pvalue(mae_diffs)
    except ValueError:
        wilcoxon_p = float("nan")
    perm_p = paired_permutation_pvalue(mae_diffs)

    det_shared = sorted(
        set(gemini["submission_run_avg_detection"]) & set(gpt["submission_run_avg_detection"])
    )
    gemini_det = gemini["submission_run_avg_detection"]
    gpt_det = gpt["submission_run_avg_detection"]
    precision_sign = compare_submission_metrics(gemini_det, gpt_det, "precision")
    recall_sign = compare_submission_metrics(gemini_det, gpt_det, "recall")

    return {
        "gpt_minus_gemini_run_avg_mae": {
            "mean": statistics.mean(mae_diffs),
            "median": statistics.median(mae_diffs),
            "n": len(mae_diffs),
            "mean_ci95": {
                "point": mae_diff_ci[0],
                "lower": mae_diff_ci[1],
                "upper": mae_diff_ci[2],
            },
            "wilcoxon_p": wilcoxon_p,
            "permutation_p": perm_p,
        },
        "precision_sign_test": precision_sign,
        "recall_sign_test": recall_sign,
    }


def analyze_sources(expert: dict[str, float], ta: dict[str, float], gemini: dict, gpt: dict) -> dict:
    shared = sorted(set(expert) & set(ta) & set(gemini["submission_run_avg_mae"]) & set(gpt["submission_run_avg_mae"]))
    gemini_runs = [load_total_scores(run["experiment"], "llm") for run in gemini["runs"]]
    gpt_runs = [load_total_scores(run["experiment"], "llm") for run in gpt["runs"]]
    gemini_avg = {sid: statistics.mean([run[sid] for run in gemini_runs]) for sid in shared}
    gpt_avg = {sid: statistics.mean([run[sid] for run in gpt_runs]) for sid in shared}

    arrays = [
        [expert[sid] for sid in shared],
        [ta[sid] for sid in shared],
        [gemini_avg[sid] for sid in shared],
        [gpt_avg[sid] for sid in shared],
    ]
    friedman_stat, friedman_p = friedman_test(*arrays)

    contrasts = []
    pairs = [
        ("GPT vs Expert", [gpt_avg[sid] - expert[sid] for sid in shared]),
        ("GPT vs TA", [gpt_avg[sid] - ta[sid] for sid in shared]),
        ("GPT vs Gemini", [gpt_avg[sid] - gemini_avg[sid] for sid in shared]),
        ("Gemini vs Expert", [gemini_avg[sid] - expert[sid] for sid in shared]),
        ("Gemini vs TA", [gemini_avg[sid] - ta[sid] for sid in shared]),
        ("TA vs Expert", [ta[sid] - expert[sid] for sid in shared]),
    ]
    raw = []
    for name, diffs in pairs:
        try:
            p = wilcoxon_pvalue(diffs)
        except ValueError:
            p = 1.0
        raw.append((name, p))
        contrasts.append(
            {
                "contrast": name,
                "mean_difference": statistics.mean(diffs),
                "median_difference": statistics.median(diffs),
                "p_raw": p,
            }
        )
    holm = {row["contrast"]: row["p_holm"] for row in holm_adjust(raw)}
    for row in contrasts:
        row["p_holm"] = holm[row["contrast"]]

    ta_abs_errors = {sid: abs(ta[sid] - expert[sid]) for sid in shared}
    absolute_error_contrasts = []
    for name, model in (("Gemini vs TA", gemini), ("GPT vs TA", gpt)):
        differences = [
            model["submission_run_avg_mae"][sid] - ta_abs_errors[sid]
            for sid in shared
        ]
        difference_ci = bootstrap_mean_ci(differences)
        absolute_error_contrasts.append(
            {
                "contrast": name,
                "definition": "model run-averaged absolute error minus TA absolute error",
                "mean_difference": statistics.mean(differences),
                "median_difference": statistics.median(differences),
                "mean_difference_ci95": {
                    "point": difference_ci[0],
                    "lower": difference_ci[1],
                    "upper": difference_ci[2],
                },
                "wilcoxon_p": wilcoxon_pvalue(differences),
                "permutation_p": paired_permutation_pvalue(differences),
                "n": len(differences),
            }
        )

    return {
        "friedman": {
            "chi2": friedman_stat,
            "p_value": friedman_p,
            "kendall_w": friedman_stat / (len(shared) * (len(arrays) - 1)),
            "n": len(shared),
        },
        "wilcoxon_contrasts_holm": contrasts,
        "absolute_error_contrasts": absolute_error_contrasts,
        "ta_vs_expert": grade_metrics(expert, ta),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_markdown(payload: dict) -> str:
    lines = ["# Multi-run Paper Benchmark", ""]
    for model_key in ("gemini", "gpt"):
        model = payload["models"][model_key]
        primary = model["primary_grade_concordance"]
        det = model["detection_primary"]
        stab = model["stability"]
        lines.extend(
            [
                f"## {model['label']}",
                "",
                f"- Primary MAE (run-averaged, n=84): {primary['mae']:.3f} "
                f"[{primary['mae_ci95']['lower']:.3f}, {primary['mae_ci95']['upper']:.3f}]",
                f"- Conventional RMSE over 252 repeated observations: {primary['rmse']:.3f} "
                f"[{primary['rmse_ci95']['lower']:.3f}, {primary['rmse_ci95']['upper']:.3f}]",
                f"- MAE range across runs: {model['run_metric_ranges']['mae']['min']:.3f}"
                f"–{model['run_metric_ranges']['mae']['max']:.3f}",
                f"- Precision mean of run means: {det['precision_mean_of_run_means']:.3f}; "
                f"Recall: {det['recall_mean_of_run_means']:.3f}",
                f"- ICC(2,1): {stab['icc_2_1']:.3f} "
                f"[{stab['icc_2_1_ci95']['lower']:.3f}, {stab['icc_2_1_ci95']['upper']:.3f}]",
                f"- Exact grade agreement (3 runs): {stab['agreement']['exact_all_runs']:.1%}",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate three-run paper analyses.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    expert = load_total_scores(BASELINE_EXPERIMENT, "expert")
    ta = load_total_scores(BASELINE_EXPERIMENT, "human")

    models = {}
    for study_key, meta in STUDIES.items():
        manifest = load_json(PROJECT_ROOT / meta["manifest"])
        models[study_key] = analyze_model(study_key, manifest, expert)

    payload = {
        "inferential_unit": "submission",
        "n_submissions": len(expert),
        "llm_assessments_per_model": 252,
        "models": models,
        "model_comparison": compare_models(models["gemini"], models["gpt"]),
        "source_comparison": analyze_sources(expert, ta, models["gemini"], models["gpt"]),
    }

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    write_json(output_dir / "paper_benchmark.json", payload)
    (output_dir / "paper_benchmark.md").write_text(render_markdown(payload) + "\n", encoding="utf-8")

    grade_rows = []
    detection_rows = []
    for model_key, model in models.items():
        for run in model["runs"]:
            grade_rows.append(
                {
                    "model": model_key,
                    "label": run["label"],
                    "experiment": run["experiment"],
                    "mae": run["mae"],
                    "rmse": run["rmse"],
                    "bias": run["bias"],
                    "within_1": run["within_1"],
                    "mean_grade": run["mean_grade"],
                }
            )
        for det in model["detection_by_run"]:
            detection_rows.append(
                {
                    "model": model_key,
                    "label": det["label"],
                    "experiment": det["experiment"],
                    "precision": det["precision"],
                    "recall": det["recall"],
                    "f1": det["f1"],
                    "tp": det["tp"],
                    "fp": det["fp"],
                    "fn": det["fn"],
                }
            )
    write_csv(output_dir / "paper_grade_per_run.csv", grade_rows)
    write_csv(output_dir / "paper_detection_per_run.csv", detection_rows)

    print(f"Wrote {output_dir / 'paper_benchmark.json'}")


if __name__ == "__main__":
    main()
