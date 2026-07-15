#!/usr/bin/env python3

import argparse
import json

from common import PROJECT_ROOT, run_step


def latest_batch_status(experiment):
    marker = (
        PROJECT_ROOT
        / "data"
        / experiment
        / "outputs"
        / "raw_api"
        / "batch_runs"
        / "latest_run.json"
    )
    if not marker.exists():
        return None
    run_id = json.loads(marker.read_text(encoding="utf-8")).get("run_id")
    if not run_id:
        return None
    state_path = marker.parent / run_id / "state.json"
    if not state_path.exists():
        return None
    return json.loads(state_path.read_text(encoding="utf-8")).get("status")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run LLM evaluation + analysis on an experiment with packaged submissions already present."
    )
    parser.add_argument("--experiment", "-e", required=True)
    parser.add_argument("--skip-llm-evaluation", action="store_true")
    parser.add_argument("--skip-analysis", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--model")
    parser.add_argument("--batch", action="store_true", help="Use OpenAI Batch API for LLM evaluation.")
    parser.add_argument("--batch-action", choices=["start", "advance", "status"], default="advance")
    parser.add_argument("--batch-run-id")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--poll-seconds", type=float)
    parser.add_argument("--max-wait-seconds", type=float)
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.skip_llm_evaluation:
        extra = []
        if args.overwrite:
            extra.append("--overwrite")
        if args.dry_run:
            extra.append("--dry-run")
        if args.limit is not None:
            extra.extend(["--limit", str(args.limit)])
        if args.model:
            extra.extend(["--model", args.model])
        if args.batch:
            extra.append("--batch")
            extra.extend(["--batch-action", args.batch_action])
            if args.batch_run_id:
                extra.extend(["--batch-run-id", args.batch_run_id])
            if args.wait:
                extra.append("--wait")
            if args.poll_seconds is not None:
                extra.extend(["--poll-seconds", str(args.poll_seconds)])
            if args.max_wait_seconds is not None:
                extra.extend(["--max-wait-seconds", str(args.max_wait_seconds)])
        run_step("src/workflows/llm_evaluation.py", args.experiment, extra)

    batch_status = latest_batch_status(args.experiment) if args.batch else None
    if args.batch and batch_status != "completed":
        print(f"Batch status is {batch_status}; skipping analysis until the batch completes.")
    elif not args.skip_analysis:
        run_step("src/workflows/analysis_reporting.py", args.experiment)


if __name__ == "__main__":
    main()
