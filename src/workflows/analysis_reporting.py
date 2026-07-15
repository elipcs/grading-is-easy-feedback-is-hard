#!/usr/bin/env python3

import argparse
from common import run_step


def parse_args():
    parser = argparse.ArgumentParser(description="Canonical Analysis & Reporting workflow.")
    parser.add_argument("--experiment", "-e", required=True)
    parser.add_argument("--taxonomy-provider", choices=["gemini", "openai", "anthropic"], default="anthropic")
    parser.add_argument("--taxonomy-model", default="claude-sonnet-5")
    parser.add_argument("--taxonomy-batch", action="store_true")
    parser.add_argument("--taxonomy-action", choices=["start", "advance", "status"], default="advance")
    parser.add_argument("--taxonomy-run-id")
    parser.add_argument("--taxonomy-wait", action="store_true")
    parser.add_argument("--taxonomy-overwrite", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()

    run_step("src/pipeline/11_consolidate_results.py", args.experiment)
    run_step("src/pipeline/12_analyze_results.py", args.experiment)
    taxonomy_extra = ["--provider", args.taxonomy_provider, "--model", args.taxonomy_model]
    if args.taxonomy_batch or args.taxonomy_provider in {"openai", "anthropic"}:
        taxonomy_extra.append("--batch")
    taxonomy_extra.extend(["--action", args.taxonomy_action])
    if args.taxonomy_run_id:
        taxonomy_extra.extend(["--run-id", args.taxonomy_run_id])
    if args.taxonomy_wait:
        taxonomy_extra.append("--wait")
    if args.taxonomy_overwrite:
        taxonomy_extra.append("--overwrite-taxonomy")
    run_step("src/pipeline/06_classify_feedback_errors.py", args.experiment, taxonomy_extra)
    run_step("src/pipeline/07_error_overlap_analysis.py", args.experiment)
    run_step("src/pipeline/08_grade_comparison_dashboard.py", args.experiment)


if __name__ == "__main__":
    main()
