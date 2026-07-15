#!/usr/bin/env python3

import argparse
import json

from common import PROJECT_ROOT, run_step


def load_experiment_provider(experiment: str) -> str:
    config_path = PROJECT_ROOT / "data" / experiment / "experiment_config.json"
    return json.loads(config_path.read_text(encoding="utf-8"))["llm_protocol"]["provider"]


def resolve_llm_script(experiment: str, use_batch: bool) -> str:
    if not use_batch:
        return "src/pipeline/03_run_llm_evaluations.py"
    provider = load_experiment_provider(experiment)
    if provider == "openai":
        return "src/pipeline/04_run_llm_evaluations_batch.py"
    if provider == "gemini":
        return "src/pipeline/05_run_llm_evaluations_gemini_batch.py"
    raise SystemExit(f"Batch LLM evaluation is not supported for provider={provider}.")


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
    parser = argparse.ArgumentParser(description="Canonical LLM Evaluation workflow.")
    parser.add_argument("--experiment", "-e", required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--model")
    parser.add_argument("--batch", action="store_true", help="Use provider Batch API for LLM evaluation.")
    parser.add_argument("--batch-action", choices=["start", "advance", "status"], default="advance")
    parser.add_argument("--batch-run-id")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--poll-seconds", type=float)
    parser.add_argument("--max-wait-seconds", type=float)
    return parser.parse_args()


def main():
    args = parse_args()
    llm_extra = []
    if args.overwrite:
        llm_extra.append("--overwrite")
    if args.dry_run:
        llm_extra.append("--dry-run")
    if args.limit is not None:
        llm_extra.extend(["--limit", str(args.limit)])
    if args.model:
        llm_extra.extend(["--model", args.model])
    if args.batch:
        llm_extra.extend(["--action", args.batch_action])
        if args.batch_run_id:
            llm_extra.extend(["--run-id", args.batch_run_id])
        if args.wait:
            llm_extra.append("--wait")
        if args.poll_seconds is not None:
            llm_extra.extend(["--poll-seconds", str(args.poll_seconds)])
        if args.max_wait_seconds is not None:
            llm_extra.extend(["--max-wait-seconds", str(args.max_wait_seconds)])

    run_step("src/pipeline/02_render_prompts.py", args.experiment)
    llm_script = resolve_llm_script(args.experiment, args.batch)
    run_step(llm_script, args.experiment, llm_extra)
    batch_status = latest_batch_status(args.experiment) if args.batch else None
    if not args.dry_run and (not args.batch or batch_status == "completed"):
        run_step("src/pipeline/05_validate_evaluations.py", args.experiment)
    elif args.batch:
        print(f"Batch status is {batch_status}; validation will run after the batch completes.")


if __name__ == "__main__":
    main()
