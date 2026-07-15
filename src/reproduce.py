#!/usr/bin/env python3
"""
One-command reproduction entry point for the SBES artifact.

Examples:

  # Recommended Functional path (no API keys): rebuild paper tables + figures
  python3 src/reproduce.py

  # Local path + triangulation + legacy single-run benchmark
  python3 src/reproduce.py --extra

  # Re-run LLM grading for all six runs (requires API keys; results may differ)
  python3 src/reproduce.py --with-apis

  # Cheap API smoke test on a few submissions
  python3 src/reproduce.py --with-apis --limit 2
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

GPT_RUNS = [
    "lab03-filmnow/runs/gpt55/run1",
    "lab03-filmnow/runs/gpt55/run2",
    "lab03-filmnow/runs/gpt55/run3",
]
GEMINI_RUNS = [
    "lab03-filmnow/runs/gemini31pro/run1",
    "lab03-filmnow/runs/gemini31pro/run2",
    "lab03-filmnow/runs/gemini31pro/run3",
]
ALL_RUNS = GEMINI_RUNS + GPT_RUNS

PAPER_DIR = ROOT / "data/lab03-filmnow/results/benchmark"
DETERMINISM_GEMINI = ROOT / "data/lab03-filmnow/results/stability/gemini"
DETERMINISM_GPT = ROOT / "data/lab03-filmnow/results/stability/gpt"
LEGACY_DIR = ROOT / "data/lab03-filmnow/results/by_category"
FIGURES_DIR = ROOT / "docs/figures"
TABLES_DIR = ROOT / "docs/tables"
GEMINI_MANIFEST = "data/lab03-filmnow/study/gemini31pro.json"
GPT_MANIFEST = "data/lab03-filmnow/study/gpt55.json"

# Category labels for the human-readable RQ2 table (paper footnote).
CATEGORY_LABELS = {
    "class_modeling": "Class Modeling",
    "list_validation": "List Validation",
    "responsibility_division": "Responsibility Division",
    "readability_docs": "Readability / Docs",
    "array_usage": "Array Usage",
    "output_format": "Output Format",
    "hashcode_equals": "HashCode / equals",
    "string_comparison": "String Comparison",
    "tests_missing": "Tests Missing",
    "other": "Other",
    "reference_usage": "Reference Usage",
    "input_handling": "Input Handling",
}
CATEGORY_ORDER = list(CATEGORY_LABELS.keys())


def run(cmd: list[str]) -> None:
    printable = " ".join(cmd)
    print(f"\n==> {printable}", flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


def py(*script_and_args: str) -> None:
    run([PYTHON, *script_and_args])


def load_dotenv_if_present() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def require_api_keys() -> None:
    load_dotenv_if_present()
    missing = [
        name
        for name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY")
        if not os.environ.get(name) or "your_" in os.environ.get(name, "").lower()
    ]
    if missing:
        raise SystemExit(
            "Missing or placeholder API keys for --with-apis: "
            + ", ".join(missing)
            + "\nCopy .env.example to .env and set real keys."
        )


def _copy_if_exists(src: Path, dest: Path) -> None:
    if src.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def write_rq2_category_detail_md(csv_path: Path, md_path: Path) -> None:
    if not csv_path.exists():
        return
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    by = {(r["label"], r["category"]): r for r in rows}
    lines = [
        "# RQ2: Diagnostic Category Distribution (Run 1)",
        "",
        "Complete twelve-category distribution referenced by the paper.",
        "Source CSV: [`model_benchmark_by_category.csv`](model_benchmark_by_category.csv).",
        "",
        "Counts collapse repeated annotations to **binary presence** per submission–category pair.",
        "Expert = annotated occurrences; Rep. = model-reported; TP/FP/FN after semantic matching.",
        "",
        "| Category | Expert | GPT Rep. | GPT TP | GPT FP | GPT FN | Gemini Rep. | Gemini TP | Gemini FP | Gemini FN |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    tot = {k: 0 for k in ("e", "gr", "gt", "gf", "gn", "mr", "mt", "mf", "mn")}
    for cat in CATEGORY_ORDER:
        g = by.get(("gpt55", cat))
        m = by.get(("gemini31pro", cat))
        if not g or not m:
            continue
        e = int(g["expected"])
        lines.append(
            f"| {CATEGORY_LABELS[cat]} | {e} | {int(g['detected'])} | {int(g['matched_reported'])} "
            f"| {int(g['FP'])} | {int(g['FN'])} | {int(m['detected'])} | {int(m['matched_reported'])} "
            f"| {int(m['FP'])} | {int(m['FN'])} |"
        )
        tot["e"] += e
        tot["gr"] += int(g["detected"])
        tot["gt"] += int(g["matched_reported"])
        tot["gf"] += int(g["FP"])
        tot["gn"] += int(g["FN"])
        tot["mr"] += int(m["detected"])
        tot["mt"] += int(m["matched_reported"])
        tot["mf"] += int(m["FP"])
        tot["mn"] += int(m["FN"])
    lines.append(
        f"| **Total** | **{tot['e']}** | **{tot['gr']}** | **{tot['gt']}** | **{tot['gf']}** | **{tot['gn']}** "
        f"| **{tot['mr']}** | **{tot['mt']}** | **{tot['mf']}** | **{tot['mn']}** |"
    )
    lines += [
        "",
        "## Precision / Recall / F1 by category (Run 1)",
        "",
        "| Category | GPT P | GPT R | GPT F1 | Gemini P | Gemini R | Gemini F1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cat in CATEGORY_ORDER:
        g = by.get(("gpt55", cat))
        m = by.get(("gemini31pro", cat))
        if not g or not m:
            continue
        lines.append(
            f"| {CATEGORY_LABELS[cat]} | {float(g['precision']):.3f} | {float(g['recall']):.3f} "
            f"| {float(g['f1']):.3f} | {float(m['precision']):.3f} | {float(m['recall']):.3f} "
            f"| {float(m['f1']):.3f} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sync_docs_tables() -> None:
    """Refresh docs/tables/ from data/lab03-filmnow/results/."""
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    copies = [
        (LEGACY_DIR / "model_benchmark_by_category.csv", TABLES_DIR / "model_benchmark_by_category.csv"),
        (LEGACY_DIR / "model_benchmark.md", TABLES_DIR / "legacy_model_benchmark.md"),
        (LEGACY_DIR / "model_statistical_tests.csv", TABLES_DIR / "model_statistical_tests.csv"),
        (PAPER_DIR / "paper_benchmark.md", TABLES_DIR / "paper_benchmark.md"),
        (PAPER_DIR / "paper_grade_per_run.csv", TABLES_DIR / "paper_grade_per_run.csv"),
        (PAPER_DIR / "paper_detection_per_run.csv", TABLES_DIR / "paper_detection_per_run.csv"),
        (DETERMINISM_GEMINI / "determinism_benchmark.md", TABLES_DIR / "determinism_gemini.md"),
        (DETERMINISM_GPT / "determinism_benchmark.md", TABLES_DIR / "determinism_gpt.md"),
    ]
    for src, dest in copies:
        _copy_if_exists(src, dest)
    write_rq2_category_detail_md(
        TABLES_DIR / "model_benchmark_by_category.csv",
        TABLES_DIR / "rq2_category_error_detail.md",
    )


def sync_triangulation_figures() -> None:
    dest = FIGURES_DIR / "triangulation"
    dest.mkdir(parents=True, exist_ok=True)
    for label, experiment in (
        ("gpt55", "lab03-filmnow/runs/gpt55/run1"),
        ("gemini31pro", "lab03-filmnow/runs/gemini31pro/run1"),
    ):
        src_dir = ROOT / "data" / experiment / "analyses/figures/gold_triangle"
        if not src_dir.exists():
            continue
        for png in src_dir.glob("*.png"):
            shutil.copy2(png, dest / f"{label}_{png.name}")


def reproduce_local(*, extra: bool) -> None:
    print("Mode: local (no API keys required)")
    for experiment in (
        "lab03-filmnow/runs/gpt55/run1",
        "lab03-filmnow/runs/gemini31pro/run1",
    ):
        py("src/pipeline/05_validate_evaluations.py", "--experiment", experiment)

    py(
        "src/pipeline/17_multi_run_paper_analysis.py",
        "--output-dir",
        str(PAPER_DIR),
    )
    py(
        "src/pipeline/16_analyze_determinism.py",
        "--study-manifest",
        GEMINI_MANIFEST,
        "--output-dir",
        str(DETERMINISM_GEMINI),
    )
    py(
        "src/pipeline/16_analyze_determinism.py",
        "--study-manifest",
        GPT_MANIFEST,
        "--output-dir",
        str(DETERMINISM_GPT),
    )
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    py(
        "src/pipeline/generate_paper_figures.py",
        "--benchmark",
        str(PAPER_DIR / "paper_benchmark.json"),
        "--output-dir",
        str(FIGURES_DIR),
    )
    for pdf in FIGURES_DIR.glob("*.pdf"):
        pdf.unlink(missing_ok=True)

    if extra:
        for experiment in (
            "lab03-filmnow/runs/gpt55/run1",
            "lab03-filmnow/runs/gemini31pro/run1",
        ):
            py("src/pipeline/09_triangular_analysis.py", "--experiment", experiment)
        py(
            "src/pipeline/10_model_benchmark.py",
            "--condition",
            "gpt55=lab03-filmnow/runs/gpt55/run1",
            "--condition",
            "gemini31pro=lab03-filmnow/runs/gemini31pro/run1",
            "--output-dir",
            str(LEGACY_DIR),
        )
        sync_triangulation_figures()

    sync_docs_tables()

    print("\nLocal reproduction finished.")
    print(f"  Paper tables: {PAPER_DIR}")
    print(f"  Docs tables:  {TABLES_DIR}")
    print(f"  Figures:      {FIGURES_DIR}")
    md = PAPER_DIR / "paper_benchmark.md"
    if md.exists():
        print(f"\nCheck headline values in {md.relative_to(ROOT)}")
    category_md = TABLES_DIR / "rq2_category_error_detail.md"
    if category_md.exists():
        print(f"Category error detail: {category_md.relative_to(ROOT)}")


def reproduce_with_apis(*, limit: int | None, overwrite: bool) -> None:
    print(
        "Mode: with-apis\n"
        "WARNING: provider models change over time. Re-running LLMs may NOT match "
        "the stored paper numbers. Prefer `python3 src/reproduce.py` (local) to verify "
        "the reported results."
    )
    require_api_keys()

    for experiment in ALL_RUNS:
        py("src/pipeline/02_render_prompts.py", "--experiment", experiment)
        llm_cmd = [
            "src/pipeline/03_run_llm_evaluations.py",
            "--experiment",
            experiment,
        ]
        if overwrite:
            llm_cmd.append("--overwrite")
        if limit is not None:
            llm_cmd.extend(["--limit", str(limit)])
        py(*llm_cmd)
        py("src/pipeline/05_validate_evaluations.py", "--experiment", experiment)
        # Semantic matching may call Anthropic when cache misses occur.
        py("src/workflows/analysis_reporting.py", "--experiment", experiment)

    reproduce_local(extra=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reproduce paper analyses locally, or optionally re-run LLM grading.",
    )
    parser.add_argument(
        "--with-apis",
        action="store_true",
        help="Re-run LLM grading for all six runs (requires API keys; may differ from paper).",
    )
    parser.add_argument(
        "--extra",
        action="store_true",
        help="Also recompute triangulation and the legacy single-run benchmark (local mode).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="With --with-apis, grade only the first N submissions per run (smoke test).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="With --with-apis, overwrite existing LLM outputs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.with_apis:
        reproduce_with_apis(limit=args.limit, overwrite=args.overwrite)
    else:
        if args.limit is not None or args.overwrite:
            raise SystemExit("--limit / --overwrite only apply with --with-apis")
        reproduce_local(extra=args.extra)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
