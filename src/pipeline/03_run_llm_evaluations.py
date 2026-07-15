#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, add_experiment_argument
from pipeline.utils.llm_execution import run_two_stage_evaluation
from pipeline.utils.normalizers import (
    normalize_feedback_items, 
    normalize_llm_payload_stage1, 
    build_student_feedback, 
    weighted_total_score, 
    normalize_confidence,
    prompt_hash
)

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_dotenv(path):
    values = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        values[key] = value
    return values


def get_api_key(env_file, provider):
    env_values = load_dotenv(env_file)
    if provider == "gemini":
        return (
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or env_values.get("GEMINI_API_KEY")
            or env_values.get("GOOGLE_API_KEY")
        )
    if provider == "openai":
        return os.environ.get("OPENAI_API_KEY") or env_values.get("OPENAI_API_KEY")
    if provider == "github":
        return os.environ.get("GITHUB_TOKEN") or env_values.get("GITHUB_TOKEN")
    return None


def list_prompt_files(prompt_dir, submission_ids, limit):
    prompt_files = sorted(prompt_dir.glob("*.stage1.md"))
    if submission_ids:
        wanted_stems = {f"{s}.stage1" for s in submission_ids}
        prompt_files = [path for path in prompt_files if path.stem in wanted_stems]
    if limit is not None:
        prompt_files = prompt_files[:limit]
    return prompt_files


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_condition(config, api_key, args, paths):
    prompt_dir = paths.rendered_prompts_dir
    result_dir = paths.results_llm
    raw_dir = paths.results_raw_api
    parsed_dir = paths.results_raw_parsed
    normalized_dir = paths.results_normalized

    if not prompt_dir.exists():
        raise SystemExit(f"Prompt directory not found: {prompt_dir}")

    s1_prompt_files = list_prompt_files(prompt_dir, args.submission_id, args.limit)
    if not s1_prompt_files:
        raise SystemExit(f"No prompts found for experiment {paths.experiment_name}.")

    model = args.model or config["llm_protocol"]["model"]
    provider = config["llm_protocol"]["provider"]
    reasoning_effort = args.reasoning_effort
    if reasoning_effort is None:
        reasoning_effort = config["llm_protocol"].get("reasoning_effort")
    rubric = load_json(paths.rubric)
    temperature = args.temperature
    
    # Prioritize flag, then config, then fallback 1.0
    rpm = args.requests_per_minute
    if rpm is None:
        rpm = config["llm_protocol"].get("requests_per_minute", 2.0)
    
    min_interval_seconds = 60.0 / rpm if rpm > 0 else 0.0
    last_request_started_at = None

    print(f"Experiment: {paths.experiment_name}")
    print(f"Provider: {provider}")
    print(f"Model: {model} (Two-Stage Execution)")
    if reasoning_effort:
        print(f"Reasoning effort: {reasoning_effort}")
    print(f"Selected prompts: {len(s1_prompt_files)}")
    if rpm > 0:
        print(f"Target rate limit: {rpm} RPM ({min_interval_seconds:.2f}s between requests)")

    for prompt1_path in s1_prompt_files:
        submission_id = prompt1_path.name.replace(".stage1.md", "")
        prompt2_path = prompt_dir / f"{submission_id}.stage2.md"
        
        result_path = result_dir / f"{submission_id}.json"
        
        # Raw save files
        s1_resp_path = raw_dir / f"{submission_id}.stage1.response.json"
        s2_resp_path = raw_dir / f"{submission_id}.stage2.response.json"
        metadata_path = raw_dir / f"{submission_id}.request.json"
        parsed_path = parsed_dir / f"{submission_id}.two_stage.parsed.json"

        if result_path.exists() and not args.overwrite:
            print(f"- {submission_id}: ignored, result already exists")
            continue

        if not prompt2_path.exists():
            print(f"- {submission_id}: ERROR - stage2 template missing, skipping.")
            continue

        prompt_s1_text = prompt1_path.read_text(encoding="utf-8")
        prompt_s2_template = prompt2_path.read_text(encoding="utf-8")
        
        request_metadata = {
            "submission_id": submission_id,
            "experiment": paths.experiment_name,
            "architecture": "two_stage",
            "provider": provider,
            "model": model,
            "temperature": temperature,
            "reasoning_effort": reasoning_effort,
            "prompt1_path": str(prompt1_path),
            "prompt2_path": str(prompt2_path),
            "prompt1_sha256": prompt_hash(prompt_s1_text),
            "prompt2_sha256": prompt_hash(prompt_s2_template),
            "protocol_hashes": {
                "evaluation_principles_sha256": file_sha256(paths.evaluation_principles),
                "feedback_style_guide_sha256": file_sha256(paths.feedback_style_guide),
                "rubric_sha256": file_sha256(paths.rubric),
                "schema_stage1_sha256": file_sha256(paths.schema_stage1),
                "schema_stage2_sha256": file_sha256(paths.schema_stage2),
            },
        }

        if args.dry_run:
            print(f"- {submission_id}: dry-run")
            continue

        if last_request_started_at is not None and min_interval_seconds > 0:
            elapsed = time.monotonic() - last_request_started_at
            if elapsed < min_interval_seconds:
                sleep_for = min_interval_seconds - elapsed
                print(f"- {submission_id}: waiting {sleep_for:.2f}s to respect RPM limit")
                time.sleep(sleep_for)

        print(f"- {submission_id}: executing Two-Stage evaluation")
        last_request_started_at = time.monotonic()
        try:
            stage1_parsed, stage2_parsed, r1, r2, parse_audit = run_two_stage_evaluation(
                provider, api_key, model, prompt_s1_text, prompt_s2_template, 
                temperature, args.timeout_seconds, args.max_retries, args.retry_default_seconds,
                reasoning_effort=reasoning_effort,
            )
        except (HTTPError, RuntimeError, URLError) as error:
            print(f"  Error executing {submission_id}: {type(error).__name__} - {error}", file=sys.stderr)
            if not args.continue_on_error:
                raise
            continue

        write_json(s1_resp_path, r1)
        write_json(s2_resp_path, r2)
        write_json(metadata_path, request_metadata)
        write_json(
            parsed_path,
            {
                "submission_id": submission_id,
                "stage1_parsed": stage1_parsed,
                "stage2_parsed": stage2_parsed,
                "parse_audit": parse_audit,
            },
        )

        # Normalize Stage 1
        normalized_criteria, force_zero = normalize_llm_payload_stage1(
            stage1_parsed, submission_id, rubric, paths
        )
        
        # Normalize Stage 2
        feedback_items = normalize_feedback_items(stage2_parsed.get("feedback_items", []), normalized_criteria, force_zero)
        # We also enforce our built string feedback if either stage2 or normalizer says so.
        # But we accept the string if the model wrote it (but it must be format safe). 
        # Using build_student_feedback directly to enforce consistency over stage 2 raw string, or we can use the model string.
        # It's safer to use build_student_feedback. 
        student_feedback = stage2_parsed.get("student_feedback")
        if force_zero or not student_feedback:
            student_feedback = build_student_feedback(feedback_items)

        normalized_output = {
            "submission_id": submission_id,
            "evaluator_type": "llm",
            "criteria": normalized_criteria,
            "total_score": weighted_total_score(normalized_criteria, rubric),
            "total_max_score": float(rubric.get("score_model", {}).get("total_max_score", 10.0)),
            "feedback_items": feedback_items,
            "student_feedback": student_feedback,
            "reviewer_audit": stage1_parsed.get("reviewer_audit", {}),
            "feedback_reviewer_notes": stage2_parsed.get("reviewer_notes", {}),
            "confidence": normalize_confidence(stage1_parsed.get("confidence"), config["confidence_labels"]),
        }
        
        write_json(result_path, normalized_output)
        write_json(normalized_dir / f"{submission_id}.normalized.json", normalized_output)
        print(f"  {submission_id}: saved to {result_path}")

        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)


def parse_args():
    parser = argparse.ArgumentParser(description="Executes Two-Stage evaluations using LLM.")
    add_experiment_argument(parser)
    parser.add_argument(
        "--submission-id",
        action="append",
        help="Can be repeated to limit execution to specific submissions.",
    )
    parser.add_argument("--limit", type=int, help="Limits the number of executed prompts.")
    parser.add_argument("--model", help="Overrides the model from config.")
    parser.add_argument("--temperature", type=float, default=0.0, help="Generation temperature.")
    parser.add_argument(
        "--reasoning-effort",
        choices=["minimal", "low", "medium", "high", "xhigh"],
        help="Reasoning effort for providers/models that support it.",
    )
    parser.add_argument(
        "--requests-per-minute",
        type=float,
        help="Target limit for requests per minute (defaults to experiment_config.json).",
    )
    parser.add_argument("--timeout-seconds", type=int, default=180, help="Timeout per request (applied stage-by-stage).")
    parser.add_argument("--sleep-seconds", type=float, default=1.0, help="Pause between requests.")
    parser.add_argument("--max-retries", type=int, default=5, help="Maximum number of retries on 429.")
    parser.add_argument(
        "--retry-default-seconds",
        type=float,
        default=15.0,
        help="Default wait time when the API does not provide retryDelay.",
    )
    parser.add_argument("--env-file", default=".env", help="Environment file relative to the repository root.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrites existing results.")
    parser.add_argument("--dry-run", action="store_true", help="Shows what would be executed without calling the API.")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continues to the next prompt even if an error occurs.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    paths = ExperimentPaths(args.experiment)
    config = load_json(paths.experiment_config)
    env_file = (EXPERIMENT_ROOT / args.env_file).resolve()
    provider = config["llm_protocol"]["provider"]
    api_key = get_api_key(env_file, provider)

    if not api_key and not args.dry_run:
        raise SystemExit(
            "API key not found. Set OPENAI_API_KEY, GEMINI_API_KEY/GOOGLE_API_KEY, "
            "or GITHUB_TOKEN according to llm_protocol.provider."
        )

    run_condition(config, api_key, args, paths)


if __name__ == "__main__":
    main()
