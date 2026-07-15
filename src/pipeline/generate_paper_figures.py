#!/usr/bin/env python3
"""
Generate comparative paper figures for the Lab03 FilmNow model benchmark.

The script accepts either:
- `model_benchmark.json` from `10_model_benchmark.py` (single run), or
- `paper_benchmark.json` from `17_multi_run_paper_analysis.py` (three-run aggregates).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCHMARK = (
    ROOT / "data" / "lab03-filmnow" / "results" / "paper" / "paper_benchmark.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "figures"
BASELINE_EXPERIMENT = "lab03-filmnow/runs/gemini31pro/run1"
PAPER_MODEL_ORDER = ("gemini", "gpt")
PAPER_MODEL_KEYS = {
    "gemini": "gemini31pro",
    "gpt": "gpt55",
}

# Premium color palette (Tailwind-inspired, calibrated for paper)
COLORS = {
    "gemini31pro": "#4F46E5",  # Indigo 600
    "gpt55": "#E11D48",        # Rose 600
    "precision": "#059669",    # Emerald 600
    "recall": "#D97706",       # Amber 600
    "f1": "#4F46E5",           # Indigo 600
}
GRAY = "#4B5563"  # Gray 600
LIGHT = "#F3F4F6" # Gray 100
DARK = "#111827"  # Gray 900

LABELS = {
    "gemini31pro": "Gemini 3.1 Pro",
    "gpt55": "GPT-5.5",
    "class_modeling": "Class Modeling",
    "tests_missing": "Tests Missing",
    "list_validation": "List Validation",
    "responsibility_division": "Responsibility Division",
    "readability_docs": "Readability / Docs",
    "output_format": "Output Format",
    "string_comparison": "String Comparison",
    "array_usage": "Array Usage",
    "hashcode_equals": "HashCode / equals",
    "reference_usage": "Reference Usage",
    "input_handling": "Input Handling",
    "other": "Other",
}

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif", "Georgia", "serif"],
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlepad": 12,
        "axes.labelsize": 10,
        "axes.labelweight": "medium",
        "axes.labelpad": 8,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "legend.frameon": True,
        "legend.edgecolor": "#E5E7EB",
        "legend.fancybox": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#9CA3AF",
        "axes.linewidth": 0.8,
        "grid.color": "#F3F4F6",
        "grid.linewidth": 0.8,
        "figure.dpi": 200,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.1,
    }
)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save(fig, output_dir: Path, stem: str):
    for suffix in (".pdf", ".png"):
        fig.savefig(output_dir / f"{stem}{suffix}")
    plt.close(fig)
    print(f"  {stem}.pdf / {stem}.png")


def ordered_conditions(payload):
    preferred = ["gemini31pro", "gpt55"]
    conditions = payload["conditions"]
    return sorted(conditions, key=lambda item: preferred.index(item["label"]) if item["label"] in preferred else 99)


def is_paper_benchmark(payload: dict) -> bool:
    return "models" in payload and "conditions" not in payload


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
        payload = load_json(path)
        scores[path.stem] = float(payload.get("total_score", 0.0))
    return scores


def count_reported_problems(llm_payload: dict) -> int:
    return sum(len(criterion.get("deductions", [])) for criterion in llm_payload.get("criteria", []))


def harmonic_mean(left: float, right: float) -> float:
    if left + right == 0:
        return 0.0
    return 2 * left * right / (left + right)


def pearson_r(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    x_arr = np.asarray(xs, dtype=float)
    y_arr = np.asarray(ys, dtype=float)
    if np.std(x_arr) == 0 or np.std(y_arr) == 0:
        return None
    return float(np.corrcoef(x_arr, y_arr)[0, 1])


def load_overlap_summary(experiment: str) -> dict:
    overlap_path = ExperimentPaths(experiment).results_analysis / "error_overlap.json"
    if not overlap_path.exists():
        return {}
    overlap = load_json(overlap_path)
    global_metrics = overlap.get("global_metrics", {})
    category_metrics = {}
    for category, metrics in overlap.get("category_metrics", {}).items():
        tp = metrics.get("TP", 0)
        fp = metrics.get("FP", 0)
        fn = metrics.get("FN", 0)
        category_metrics[category] = {
            "expected": tp + fn,
            "detected": tp + fp,
            "matched_reported": tp,
            "FP": fp,
            "FN": fn,
            "precision": metrics.get("Precision", 0),
            "recall": metrics.get("Recall", 0),
            "f1": metrics.get("F1", 0),
        }
    intersection = global_metrics.get("intersection", 0)
    total_detected = global_metrics.get("total_llm_found", 0)
    total_expected = global_metrics.get("total_expected", 0)
    return {
        "matched_reported_problems": intersection,
        "false_positive_problems": total_detected - intersection,
        "false_negative_problems": total_expected - intersection,
        "category_metrics": category_metrics,
    }


def build_paper_benchmark_conditions(payload: dict) -> list[dict]:
    expert = load_total_scores(BASELINE_EXPERIMENT, "expert")
    conditions = []
    for model_key in PAPER_MODEL_ORDER:
        model = payload["models"][model_key]
        label = PAPER_MODEL_KEYS[model_key]
        primary = model["primary_grade_concordance"]
        detection = model["detection_primary"]
        precision = detection["precision_mean_of_run_means"]
        recall = detection["recall_mean_of_run_means"]
        experiments = [run["experiment"] for run in model["runs"]]
        run_score_sets = [load_total_scores(experiment, "llm") for experiment in experiments]
        shared = sorted(set(expert) & set.intersection(*(set(scores) for scores in run_score_sets)))
        run_avg_grades = {
            submission_id: float(np.mean([scores[submission_id] for scores in run_score_sets]))
            for submission_id in shared
        }
        scatter_points = [
            {
                "submission_id": submission_id,
                "expert": expert[submission_id],
                "llm": run_avg_grades[submission_id],
            }
            for submission_id in shared
        ]
        problem_counts = []
        bias_points = []
        bias_scatter = []
        for submission_id in shared:
            counts = []
            for experiment in experiments:
                llm_path = ExperimentPaths(experiment).results_llm / f"{submission_id}.json"
                if llm_path.exists():
                    counts.append(count_reported_problems(load_json(llm_path)))
            if counts:
                mean_count = float(np.mean(counts))
                bias = run_avg_grades[submission_id] - expert[submission_id]
                problem_counts.append(mean_count)
                bias_points.append(bias)
                bias_scatter.append((mean_count, bias))
        overlap_summary = load_overlap_summary(experiments[0])
        conditions.append(
            {
                "label": label,
                "experiment": experiments[0],
                "grade_mae": primary["mae"],
                "grade_rmse": primary["rmse"],
                "grade_bias": primary["bias"],
                "overlap_precision": precision,
                "overlap_recall": recall,
                "overlap_f1": harmonic_mean(precision, recall),
                "submission_run_avg_mae": model["submission_run_avg_mae"],
                "run_avg_grades": run_avg_grades,
                "scatter_points": scatter_points,
                "bias_scatter": bias_scatter,
                "bias_correlation": {
                    "pearson_r": pearson_r(problem_counts, bias_points),
                },
                **overlap_summary,
            }
        )
    return conditions


def scatter_points(condition):
    if condition.get("scatter_points"):
        return condition["scatter_points"]
    paths = ExperimentPaths(condition["experiment"])
    grade = load_json(paths.results_analysis / "grade_comparison.json")
    return grade["overall"]["scatter_points"]


def fig_rq1_model_grade_metrics(conditions, output_dir):
    metrics = [
        ("grade_mae", "MAE"),
        ("grade_rmse", "RMSE"),
        ("grade_bias", "Bias"),
    ]
    x = np.arange(len(metrics))
    width = 0.34

    fig, ax = plt.subplots(figsize=(4.8, 3.0))
    all_values = []
    for offset, condition in zip([-width / 2, width / 2], conditions):
        values = [condition[key] for key, _ in metrics]
        all_values.extend(values)
        bars = ax.bar(
            x + offset,
            values,
            width,
            label=LABELS.get(condition["label"], condition["label"]),
            color=COLORS.get(condition["label"], GRAY),
            alpha=0.88,
            zorder=2,
        )
        for bar, value in zip(bars, values):
            va = "bottom" if value >= 0 else "top"
            pad = 0.04 if value >= 0 else -0.06
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + pad,
                f"{value:.2f}",
                ha="center",
                va=va,
                fontsize=7.5,
            )

    ax.axhline(0, color=GRAY, linewidth=1.0, zorder=3)
    ax.axhline(1.0, color=GRAY, linestyle="--", linewidth=0.8, alpha=0.5, label="1.0 pt tolerance", zorder=1)
    ax.set_xticks(x)
    ax.set_xticklabels([label for _, label in metrics])
    ax.set_ylim(min(all_values) - 0.5, max(all_values) + 0.5)
    ax.set_ylabel("Points on 0-10 scale")
    ax.set_title("RQ1: Grade Concordance by Model")
    ax.grid(True, axis="y", zorder=0)
    ax.legend(loc="best", framealpha=0.9)
    save(fig, output_dir, "fig_rq1_model_grade_metrics")


def load_ta_errors() -> list[float]:
    paths = ExperimentPaths(BASELINE_EXPERIMENT)
    expert_dir = paths.results_gold_standard
    human_dir = paths.results_human
    ta_errors = []
    for fp in human_dir.glob("*.json"):
        sid = fp.stem
        expert_fp = expert_dir / f"{sid}.json"
        if expert_fp.exists():
            ta_score = load_json(fp)["total_score"]
            expert_score = load_json(expert_fp)["total_score"]
            ta_errors.append(abs(float(ta_score) - float(expert_score)))
    return ta_errors


def fig_rq1_error_distribution(conditions, output_dir):
    fig, ax = plt.subplots(figsize=(4.8, 3.0))
    data = []
    labels = []
    colors_list = []

    ta_errors = load_ta_errors()
    if ta_errors:
        data.append(ta_errors)
        labels.append("TA")
        colors_list.append("#6B7280")  # Gray 500

    # Add model errors
    for condition in conditions:
        if condition.get("submission_run_avg_mae"):
            errors = list(condition["submission_run_avg_mae"].values())
        else:
            points = scatter_points(condition)
            errors = [abs(float(row["llm"]) - float(row["expert"])) for row in points]
        data.append(errors)
        labels.append(LABELS.get(condition["label"], condition["label"]))
        colors_list.append(COLORS.get(condition["label"], GRAY))

    box = ax.boxplot(
        data,
        tick_labels=labels,
        patch_artist=True,
        widths=0.55,
        medianprops={"color": "black", "linewidth": 1.2},
    )
    for patch, color in zip(box["boxes"], colors_list):
        patch.set_facecolor(color)
        patch.set_alpha(0.35)
        patch.set_edgecolor(color)

    for i, errors in enumerate(data):
        jitter = np.linspace(-0.08, 0.08, len(errors))
        ax.scatter(
            np.full(len(errors), i + 1) + jitter,
            sorted(errors),
            s=8,
            alpha=0.35,
            color=colors_list[i],
            edgecolors="none",
            zorder=2,
        )

    ax.axhline(1.0, color=GRAY, linestyle="--", linewidth=0.8, alpha=0.6, label="±1.0 tolerance")
    ax.axhline(2.0, color=GRAY, linestyle=":", linewidth=0.8, alpha=0.4, label="±2.0")
    ax.set_ylabel("Absolute error |grade - expert|")
    ax.set_title("RQ1: Error Distribution by Evaluator")
    ax.grid(True, axis="y")
    ax.legend(loc="upper left")
    save(fig, output_dir, "fig_rq1_error_distribution_by_model")


def fig_rq1_grade_distribution(conditions, output_dir):
    fig, ax = plt.subplots(figsize=(4.8, 3.2))

    data = []
    labels = []
    colors = []

    # Expert Reference as baseline
    paths = ExperimentPaths(BASELINE_EXPERIMENT)
    expert_dir = paths.results_gold_standard
    expert_grades = [load_json(fp)["total_score"] for fp in expert_dir.glob("*.json")]

    if expert_grades:
        data.append(expert_grades)
        labels.append("Expert")
        colors.append(GRAY)

    # TA grades (from human/monitor)
    human_dir = paths.results_human
    ta_grades = [load_json(fp)["total_score"] for fp in human_dir.glob("*.json")]

    if ta_grades:
        data.append(ta_grades)
        labels.append("TA")
        colors.append("#6B7280")  # Gray 500

    for condition in conditions:
        if condition.get("run_avg_grades"):
            llm_grades = list(condition["run_avg_grades"].values())
        else:
            llm_dir = ExperimentPaths(condition["experiment"]).results_llm
            llm_grades = [load_json(fp)["total_score"] for fp in llm_dir.glob("*.json")]

        if llm_grades:
            data.append(llm_grades)
            labels.append(LABELS.get(condition["label"], condition["label"]))
            colors.append(COLORS.get(condition["label"], GRAY))

    if not data:
        return

    box = ax.boxplot(
        data,
        tick_labels=labels,
        patch_artist=True,
        widths=0.6,
        medianprops={"color": "white", "linewidth": 1.5},
    )

    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.5)
        patch.set_edgecolor(color)
        patch.set_linewidth(1.2)

    # Optional: add individual points (jitter)
    for i, grades in enumerate(data, start=1):
        x = np.random.normal(i, 0.04, size=len(grades))
        ax.scatter(x, grades, alpha=0.3, color=colors[i-1], s=10, edgecolors="none")

    ax.set_ylabel("Grade (0-10)")
    ax.set_ylim(-0.5, 10.5)
    ax.set_title("RQ1: Grade Distribution Comparison")
    ax.grid(True, axis="y")
    save(fig, output_dir, "fig_rq1_grade_distribution")


def fig_rq1_bias_correlation(conditions, output_dir):
    fig, ax = plt.subplots(figsize=(4.8, 3.2))

    for condition in conditions:
        label = LABELS.get(condition["label"], condition["label"])
        color = COLORS.get(condition["label"], GRAY)

        if condition.get("bias_scatter"):
            points = condition["bias_scatter"]
        else:
            paths = ExperimentPaths(condition["experiment"])
            llm_dir = paths.results_llm
            expert_dir = paths.results_gold_standard
            points = []
            for fp in llm_dir.glob("*.json"):
                sid = fp.stem
                expert_fp = expert_dir / f"{sid}.json"
                if not expert_fp.exists():
                    continue
                llm_data = load_json(fp)
                expert_data = load_json(expert_fp)
                n_problems = count_reported_problems(llm_data)
                bias = float(llm_data["total_score"]) - float(expert_data["total_score"])
                points.append((n_problems, bias))

        if not points:
            continue

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]

        ax.scatter(xs, ys, alpha=0.4, color=color, label=label, s=15, edgecolors="none")

        # Trend line
        z = np.polyfit(xs, ys, 1)
        p = np.poly1d(z)
        xp = np.linspace(min(xs), max(xs), 100)
        ax.plot(xp, p(xp), color=color, linestyle="--", linewidth=1.2, alpha=0.8)

        # Display R value from benchmark if available
        corr = condition.get("bias_correlation", {}).get("pearson_r")
        if corr is not None:
            ax.text(max(xs), p(max(xs)), f" r={corr:.2f}", color=color, va="center", fontsize=8, weight="bold")

    ax.axhline(0, color=GRAY, linewidth=0.8, zorder=1)
    ax.set_xlabel("Number of Diagnostic Issues Reported by LLM")
    ax.set_ylabel("Grade Bias (LLM - Expert)")
    ax.set_title("Bias Correlation: Model Severity vs. Error Volume")
    ax.grid(True, linestyle=":", alpha=0.4)
    ax.legend(loc="upper right")
    save(fig, output_dir, "fig_rq1_bias_correlation")


def fig_rq2_model_detection_metrics(conditions, output_dir):
    metrics = [
        ("overlap_precision", "Precision"),
        ("overlap_recall", "Recall"),
        ("overlap_f1", "F1"),
    ]
    x = np.arange(len(metrics))
    width = 0.34

    fig, ax = plt.subplots(figsize=(4.8, 3.0))
    for offset, condition in zip([-width / 2, width / 2], conditions):
        values = [condition[key] for key, _ in metrics]
        bars = ax.bar(
            x + offset,
            values,
            width,
            label=LABELS.get(condition["label"], condition["label"]),
            color=COLORS.get(condition["label"], GRAY),
            alpha=0.88,
            zorder=2,
        )
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.015,
                f"{value:.2f}",
                ha="center",
                va="bottom",
                fontsize=7.5,
            )

    ax.set_xticks(x)
    ax.set_xticklabels([label for _, label in metrics])
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Diagnostic score")
    ax.set_title("RQ2: Diagnostic Alignment Metrics")
    ax.grid(True, axis="y", zorder=0)
    ax.legend(loc="upper left")
    save(fig, output_dir, "fig_rq2_model_detection_metrics")


def fig_rq2_category_performance(conditions, output_dir):
    if not all("category_metrics" in condition for condition in conditions):
        print("  Skipping fig_rq2_category_f1_by_model (category metrics unavailable)")
        return
    categories = sorted(
        {
            category
            for condition in conditions
            for category in condition["category_metrics"]
            if category != "other"
        }
    )
    categories = sorted(
        categories,
        key=lambda category: max(condition["category_metrics"].get(category, {}).get("f1", 0) for condition in conditions),
    )
    y = np.arange(len(categories))
    height = 0.34

    fig, ax = plt.subplots(figsize=(6.2, 4.5))
    for offset, condition in zip([-height / 2, height / 2], conditions):
        values = [condition["category_metrics"].get(category, {}).get("f1", 0) for category in categories]
        ax.barh(
            y + offset,
            values,
            height,
            label=LABELS.get(condition["label"], condition["label"]),
            color=COLORS.get(condition["label"], GRAY),
            alpha=0.86,
            zorder=2,
        )

    ax.set_yticks(y)
    ax.set_yticklabels([LABELS.get(category, category) for category in categories])
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("F1")
    ax.set_title("RQ2: F1 by Diagnostic Category")
    ax.grid(True, axis="x", color=LIGHT, linewidth=0.4, zorder=0)
    ax.legend(loc="lower right")
    save(fig, output_dir, "fig_rq2_category_f1_by_model")


def fig_rq2_false_positives(conditions, output_dir):
    if not all("matched_reported_problems" in condition for condition in conditions):
        print("  Skipping fig_rq2_detection_counts_by_model (overlap counts unavailable)")
        return
    labels = [LABELS.get(condition["label"], condition["label"]) for condition in conditions]
    matched = [condition["matched_reported_problems"] for condition in conditions]
    fp = [condition["false_positive_problems"] for condition in conditions]
    fn = [condition["false_negative_problems"] for condition in conditions]
    x = np.arange(len(conditions))
    width = 0.24

    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    ax.bar(x - width, matched, width, label="Matched reported", color=COLORS["precision"], alpha=0.88, zorder=2, edgecolor="white", linewidth=0.5)
    ax.bar(x, fp, width, label="FP", color=COLORS["recall"], alpha=0.84, zorder=2, edgecolor="white", linewidth=0.5)
    ax.bar(x + width, fn, width, label="FN", color=COLORS["gpt55"], alpha=0.80, zorder=2, edgecolor="white", linewidth=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Problem count")
    ax.set_title("RQ2: Diagnostic Issue Counts by Model")
    ax.grid(True, axis="y", color=LIGHT, linewidth=0.4, zorder=0)
    ax.legend()
    save(fig, output_dir, "fig_rq2_detection_counts_by_model")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate comparative paper figures.")
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = load_json(args.benchmark)
    if is_paper_benchmark(payload):
        conditions = build_paper_benchmark_conditions(payload)
        benchmark_kind = "paper (three-run aggregates)"
    else:
        conditions = ordered_conditions(payload)
        benchmark_kind = "single-run model benchmark"

    print(f"Generating figures in {args.output_dir} from {benchmark_kind}")
    fig_rq1_model_grade_metrics(conditions, args.output_dir)
    fig_rq1_error_distribution(conditions, args.output_dir)
    fig_rq1_grade_distribution(conditions, args.output_dir)
    fig_rq1_bias_correlation(conditions, args.output_dir)
    fig_rq2_model_detection_metrics(conditions, args.output_dir)
    fig_rq2_category_performance(conditions, args.output_dir)
    fig_rq2_false_positives(conditions, args.output_dir)


if __name__ == "__main__":
    main()
