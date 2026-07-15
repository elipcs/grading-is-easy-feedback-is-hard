#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, PROJECT_ROOT
from pipeline.utils.determinism import (
    all_runs,
    count_llm_outputs_safe,
    load_json,
    load_study_manifest,
    submissions_needing_retry,
    write_json,
)
from workflows.common import run_step


DEFAULT_GEMINI_MANIFEST = PROJECT_ROOT / "data/lab03-filmnow/study/gemini31pro.json"
DEFAULT_GPT_MANIFEST = PROJECT_ROOT / "data/lab03-filmnow/study/gpt55.json"


def resolve_manifest(path: str | None) -> Path:
    if path:
        manifest_path = Path(path)
        if not manifest_path.is_absolute():
            manifest_path = PROJECT_ROOT / manifest_path
        return manifest_path
    if DEFAULT_GEMINI_MANIFEST.exists():
        return DEFAULT_GEMINI_MANIFEST
    return DEFAULT_GPT_MANIFEST


def default_output_dir(manifest: dict) -> Path:
    study = manifest.get("study", "determinism")
    if "gemini" in study:
        return PROJECT_ROOT / "data/lab03-filmnow/results/stability/gemini"
    if "gpt" in study:
        return PROJECT_ROOT / "data/lab03-filmnow/results/stability/gpt"
    return PROJECT_ROOT / "data/lab03-filmnow/results/stability/custom"


def clean_generated_outputs(experiment_dir: Path) -> None:
    for relative in (
        "outputs/llm",
        "outputs/normalized",
        "outputs/raw_parsed",
        "outputs/raw_api",
        "outputs/consolidated",
        "analyses",
    ):
        target = experiment_dir / relative
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)


def command_setup(args: argparse.Namespace) -> None:
    manifest = load_study_manifest(resolve_manifest(args.study_manifest))
    baseline = PROJECT_ROOT / "data" / manifest["baseline_experiment"]
    if not baseline.exists():
        raise SystemExit(f"Baseline experiment not found: {baseline}")

    for repeat in manifest["repeat_experiments"]:
        target = PROJECT_ROOT / "data" / repeat
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(baseline, target)
        clean_generated_outputs(target)

        config_path = target / "experiment_config.json"
        config = load_json(config_path, {}) or {}
        config["experiment_id"] = repeat
        config["experiment_name"] = f"{config.get('experiment_name', repeat)} (determinism {repeat.rsplit('-', 1)[-1]})"
        config["determinism_study"] = {
            "baseline_experiment": manifest["baseline_experiment"],
            "run_label": repeat.rsplit("-", 1)[-1],
            "purpose": "repeat grading run for determinism verification",
            "execution_mode": manifest.get("execution_mode"),
        }
        write_json(config_path, config)
        print(f"Prepared {repeat}")


def command_run(args: argparse.Namespace) -> None:
    manifest = load_study_manifest(resolve_manifest(args.study_manifest))
    extra = ["--batch", "--batch-action", args.batch_action]
    if args.wait:
        extra.append("--wait")
    if args.poll_seconds is not None:
        extra.extend(["--poll-seconds", str(args.poll_seconds)])

    for entry in all_runs(manifest):
        if entry["label"] == "run1" and not args.include_baseline:
            print(f"Skipping baseline run: {entry['experiment']}")
            continue
        run_step("src/workflows/llm_evaluation.py", entry["experiment"], extra)


def command_retry_failed(args: argparse.Namespace) -> None:
    manifest = load_study_manifest(resolve_manifest(args.study_manifest))
    for entry in all_runs(manifest):
        experiment = entry["experiment"]
        retry_ids = submissions_needing_retry(experiment, expected_count=args.expected_count)
        if not retry_ids:
            print(f"{experiment}: no missing submissions")
            continue
        extra = ["--overwrite"]
        for submission_id in retry_ids:
            extra.extend(["--submission-id", submission_id])
        print(f"{experiment}: retrying {', '.join(retry_ids)}")
        run_step("src/pipeline/03_run_llm_evaluations.py", experiment, extra)


def command_validate(args: argparse.Namespace) -> None:
    manifest = load_study_manifest(resolve_manifest(args.study_manifest))
    for entry in all_runs(manifest):
        run_step("src/pipeline/05_validate_evaluations.py", entry["experiment"])


def command_analyze(args: argparse.Namespace) -> None:
    manifest = load_study_manifest(resolve_manifest(args.study_manifest))
    extra = [
        "--taxonomy-provider",
        args.taxonomy_provider,
        "--taxonomy-model",
        args.taxonomy_model,
    ]
    if args.taxonomy_batch:
        extra.append("--taxonomy-batch")
    if args.taxonomy_overwrite:
        extra.append("--taxonomy-overwrite")
    if args.taxonomy_wait:
        extra.append("--taxonomy-wait")

    for entry in all_runs(manifest):
        run_step("src/workflows/analysis_reporting.py", entry["experiment"], extra)


def command_consolidate(args: argparse.Namespace) -> None:
    manifest = load_study_manifest(resolve_manifest(args.study_manifest))
    output_dir = Path(args.output_dir) if args.output_dir else default_output_dir(manifest)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    incomplete = []
    complete_runs = 0
    for entry in all_runs(manifest):
        count = count_llm_outputs_safe(entry["experiment"])
        if count < args.min_outputs:
            incomplete.append(f"{entry['experiment']} ({count})")
        else:
            complete_runs += 1

    if complete_runs < 2:
        print(
            "Skipping determinism consolidation: at least two completed runs are required. "
            f"Found {complete_runs} usable run(s)."
        )
        if incomplete:
            print("Incomplete runs: " + ", ".join(incomplete))
        return

    if incomplete and not args.allow_incomplete:
        raise SystemExit(
            "Incomplete runs detected: "
            + ", ".join(incomplete)
            + ". Use --allow-incomplete to consolidate anyway."
        )

    command = [
        sys.executable,
        str(PROJECT_ROOT / "src/pipeline/16_analyze_determinism.py"),
        "--study-manifest",
        str(resolve_manifest(args.study_manifest)),
        "--output-dir",
        str(output_dir),
        "--min-outputs",
        str(args.min_outputs),
    ]
    if args.allow_incomplete:
        command.append("--allow-incomplete")
    print(" ".join(command))
    subprocess.run(command, check=True)


def command_all_local(args: argparse.Namespace) -> None:
    command_validate(args)
    command_analyze(args)
    command_consolidate(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Determinism study workflow for repeated LLM grading runs.")
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--study-manifest",
        help="Path to study manifest JSON. Defaults to Gemini manifest if present.",
    )
    parent.add_argument("--expected-count", type=int, default=84)
    parent.add_argument("--min-outputs", type=int, default=84)
    parent.add_argument("--output-dir")
    parent.add_argument("--allow-incomplete", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("setup", parents=[parent], help="Create repeat experiment folders from baseline.")

    run_parser = subparsers.add_parser("run", parents=[parent], help="Run batch LLM evaluation for repeat runs.")
    run_parser.add_argument("--batch-action", choices=["start", "advance", "status"], default="start")
    run_parser.add_argument("--wait", action="store_true")
    run_parser.add_argument("--poll-seconds", type=float)
    run_parser.add_argument("--include-baseline", action="store_true")

    subparsers.add_parser(
        "retry-failed",
        parents=[parent],
        help="Retry missing or stage-1 failed submissions synchronously.",
    )
    subparsers.add_parser("validate", parents=[parent], help="Validate structured outputs for all runs.")
    subparsers.add_parser("consolidate", parents=[parent], help="Build determinism benchmark across runs.")

    analyze_parser = subparsers.add_parser("analyze", parents=[parent], help="Run analysis_reporting for all runs.")
    analyze_parser.add_argument("--taxonomy-provider", choices=["gemini", "openai", "anthropic"], default="anthropic")
    analyze_parser.add_argument("--taxonomy-model", default="claude-sonnet-5")
    analyze_parser.add_argument("--taxonomy-batch", action="store_true")
    analyze_parser.add_argument("--taxonomy-overwrite", action="store_true")
    analyze_parser.add_argument("--taxonomy-wait", action="store_true")

    all_local_parser = subparsers.add_parser(
        "all-local",
        parents=[parent],
        help="Validate, analyze, and consolidate without rerunning grading.",
    )
    all_local_parser.add_argument("--taxonomy-provider", choices=["gemini", "openai", "anthropic"], default="anthropic")
    all_local_parser.add_argument("--taxonomy-model", default="claude-sonnet-5")
    all_local_parser.add_argument("--taxonomy-batch", action="store_true")
    all_local_parser.add_argument("--taxonomy-overwrite", action="store_true")
    all_local_parser.add_argument("--taxonomy-wait", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "setup":
        command_setup(args)
    elif args.command == "run":
        command_run(args)
    elif args.command == "retry-failed":
        command_retry_failed(args)
    elif args.command == "validate":
        command_validate(args)
    elif args.command == "analyze":
        command_analyze(args)
    elif args.command == "consolidate":
        command_consolidate(args)
    elif args.command == "all-local":
        command_all_local(args)
    else:
        raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
