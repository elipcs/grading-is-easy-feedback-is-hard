#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, add_experiment_argument
from pipeline.utils.llm_execution import (
    build_gemini_batch_inline_request,
    extract_text,
    robust_json_loads,
    strip_markdown_fences,
)
from pipeline.utils.normalizers import (
    build_student_feedback,
    normalize_confidence,
    normalize_feedback_items,
    normalize_llm_payload_stage1,
    prompt_hash,
    weighted_total_score,
)

try:
    from google import genai
except ImportError:
    genai = None


EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
GEMINI_TERMINAL_BATCH_STATUSES = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED"}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dotenv(path: Path) -> dict[str, str]:
    values = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def get_gemini_api_key(env_file: Path) -> str | None:
    env_values = load_dotenv(env_file)
    return (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or env_values.get("GEMINI_API_KEY")
        or env_values.get("GOOGLE_API_KEY")
    )


def list_prompt_files(prompt_dir: Path, submission_ids: list[str] | None, limit: int | None) -> list[Path]:
    prompt_files = sorted(prompt_dir.glob("*.stage1.md"))
    if submission_ids:
        wanted_stems = {f"{submission_id}.stage1" for submission_id in submission_ids}
        prompt_files = [path for path in prompt_files if path.stem in wanted_stems]
    if limit is not None:
        prompt_files = prompt_files[:limit]
    return prompt_files


def batch_runs_dir(paths: ExperimentPaths) -> Path:
    return paths.results_raw_api / "batch_runs"


def latest_run_path(paths: ExperimentPaths) -> Path:
    return batch_runs_dir(paths) / "latest_run.json"


def run_dir(paths: ExperimentPaths, run_id: str) -> Path:
    return batch_runs_dir(paths) / run_id


def state_path(paths: ExperimentPaths, run_id: str) -> Path:
    return run_dir(paths, run_id) / "state.json"


def save_state(paths: ExperimentPaths, state: dict) -> None:
    write_json(state_path(paths, state["run_id"]), state)
    write_json(latest_run_path(paths), {"run_id": state["run_id"], "updated_at": utc_timestamp()})


def load_state(paths: ExperimentPaths, run_id: str) -> dict:
    return load_json(state_path(paths, run_id))


def resolve_latest_run_id(paths: ExperimentPaths) -> str | None:
    marker = latest_run_path(paths)
    if not marker.exists():
        return None
    payload = load_json(marker)
    return payload.get("run_id")


def gemini_client(api_key: str):
    if genai is None:
        raise SystemExit("google-genai package not installed. Run: python3 -m pip install google-genai")
    return genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})


def create_gemini_batch(client, model: str, requests: list[dict], display_name: str):
    return client.batches.create(
        model=model,
        src={"inlined_requests": requests},
        config={"display_name": display_name},
    )


def retrieve_gemini_batch(client, batch_name: str):
    return client.batches.get(name=batch_name)


def select_submissions(config: dict, args: argparse.Namespace, paths: ExperimentPaths) -> list[dict]:
    prompt_dir = paths.rendered_prompts_dir
    prompt_files = list_prompt_files(prompt_dir, args.submission_id, args.limit)
    if not prompt_files:
        raise SystemExit(f"No prompts found for experiment {paths.experiment_name}.")

    selected = []
    for prompt1_path in prompt_files:
        submission_id = prompt1_path.name.replace(".stage1.md", "")
        prompt2_path = prompt_dir / f"{submission_id}.stage2.md"
        result_path = paths.results_llm / f"{submission_id}.json"
        if result_path.exists() and not args.overwrite:
            print(f"- {submission_id}: ignored, result already exists")
            continue
        if not prompt2_path.exists():
            print(f"- {submission_id}: ERROR - stage2 template missing, skipping.")
            continue
        selected.append(
            {
                "submission_id": submission_id,
                "prompt1_path": str(prompt1_path),
                "prompt2_path": str(prompt2_path),
            }
        )

    if not selected:
        raise SystemExit("No submissions selected for batch execution.")
    return selected


def build_request_metadata(
    paths: ExperimentPaths,
    state: dict,
    submission: dict,
    prompt_s1_text: str,
    prompt_s2_template: str,
) -> dict:
    return {
        "submission_id": submission["submission_id"],
        "experiment": paths.experiment_name,
        "architecture": "two_stage",
        "execution_mode": "gemini_batch",
        "provider": "gemini",
        "model": state["model"],
        "temperature": state["temperature"],
        "reasoning_effort": state.get("reasoning_effort"),
        "batch_run_id": state["run_id"],
        "stage1_batch_name": state.get("stage1", {}).get("batch_name"),
        "stage2_batch_name": state.get("stage2", {}).get("batch_name"),
        "prompt1_path": submission["prompt1_path"],
        "prompt2_path": submission["prompt2_path"],
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


def response_to_dict(response) -> dict:
    if isinstance(response, dict):
        payload = response
    elif hasattr(response, "model_dump"):
        payload = response.model_dump(mode="json")
    elif hasattr(response, "to_dict"):
        payload = response.to_dict()
    else:
        payload = json.loads(json.dumps(response, default=str))
    return json.loads(json.dumps(payload, default=_json_default))


def _json_default(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def extract_gemini_response_text(response) -> str:
    payload = response_to_dict(response)
    return strip_markdown_fences(extract_text(payload))


def collect_gemini_batch_responses(job) -> list:
    responses = []
    if hasattr(job, "dest") and job.dest and hasattr(job.dest, "inlined_responses") and job.dest.inlined_responses:
        for resp_item in job.dest.inlined_responses:
            if hasattr(resp_item, "response") and resp_item.response:
                responses.append(resp_item.response)
    return responses


def submit_stage1_batch(
    api_key: str,
    config: dict,
    args: argparse.Namespace,
    paths: ExperimentPaths,
) -> dict:
    model = args.model or config["llm_protocol"]["model"]
    reasoning_effort = args.reasoning_effort
    if reasoning_effort is None:
        reasoning_effort = config["llm_protocol"].get("reasoning_effort")
    temperature = args.temperature
    if temperature is None:
        temperature = config["llm_protocol"].get("temperature", 0.0)

    run_id = args.run_id or f"{paths.experiment_name}-grading-gemini-{utc_timestamp()}"
    state = {
        "run_id": run_id,
        "status": "created",
        "experiment": paths.experiment_name,
        "created_at": utc_timestamp(),
        "updated_at": utc_timestamp(),
        "provider": "gemini",
        "model": model,
        "temperature": temperature,
        "reasoning_effort": reasoning_effort,
        "submissions": select_submissions(config, args, paths),
        "stage1": {},
        "stage2": {},
    }

    gemini_requests = []
    submission_ids = []
    for submission in state["submissions"]:
        submission_id = submission["submission_id"]
        prompt_text = Path(submission["prompt1_path"]).read_text(encoding="utf-8")
        gemini_requests.append(
            build_gemini_batch_inline_request(
                prompt_text,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                metadata={"submission_id": submission_id, "stage": "stage1"},
            )
        )
        submission_ids.append(submission_id)

    current_run_dir = run_dir(paths, run_id)
    write_json(current_run_dir / "stage1.input.json", gemini_requests)
    state["stage1"]["submission_ids"] = submission_ids
    state["stage1"]["request_count"] = len(gemini_requests)

    if args.dry_run:
        state["status"] = "dry_run"
        state["updated_at"] = utc_timestamp()
        save_state(paths, state)
        print(f"Stage 1 batch input written to {current_run_dir / 'stage1.input.json'}")
        print("Dry-run only; no Stage 1 Gemini batch was submitted.")
        return state

    client = gemini_client(api_key)
    batch_job = create_gemini_batch(
        client,
        model,
        gemini_requests,
        display_name=f"{run_id}-stage1",
    )
    write_json(current_run_dir / "stage1.batch.json", {"name": batch_job.name, "state": str(batch_job.state)})

    state["stage1"].update(
        {
            "batch_name": batch_job.name,
            "batch_status": batch_job.state.name,
            "submitted_at": utc_timestamp(),
        }
    )
    state["status"] = "stage1_submitted"
    state["updated_at"] = utc_timestamp()
    save_state(paths, state)
    print(f"Stage 1 Gemini batch submitted: {batch_job.name} ({batch_job.state.name})")
    return state


def refresh_stage_batch(api_key: str, args: argparse.Namespace, paths: ExperimentPaths, state: dict, stage: str) -> dict:
    stage_state = state[stage]
    batch_name = stage_state.get("batch_name")
    if not batch_name:
        return state

    client = gemini_client(api_key)
    job = retrieve_gemini_batch(client, batch_name)
    write_json(run_dir(paths, state["run_id"]) / f"{stage}.batch.json", {"name": job.name, "state": job.state.name})
    stage_state.update(
        {
            "batch_status": job.state.name,
            "last_checked_at": utc_timestamp(),
        }
    )
    state["updated_at"] = utc_timestamp()
    save_state(paths, state)
    print(f"{stage}: batch {batch_name} is {job.state.name}")
    return state, job


def process_stage1_outputs(
    api_key: str,
    args: argparse.Namespace,
    paths: ExperimentPaths,
    state: dict,
    job,
) -> dict:
    if state["stage1"].get("processed_at"):
        return state

    responses = collect_gemini_batch_responses(job)
    submission_ids = state["stage1"].get("submission_ids", [])
    if len(responses) != len(submission_ids):
        raise RuntimeError(
            f"Stage 1 response count mismatch: expected {len(submission_ids)}, got {len(responses)}"
        )

    parsed_by_submission = {}
    errors = []
    for submission_id, response in zip(submission_ids, responses):
        try:
            response_body = response_to_dict(response)
            raw_text = extract_gemini_response_text(response)
            parsed, parse_meta = robust_json_loads(raw_text)
        except Exception as error:
            errors.append({"submission_id": submission_id, "error": str(error)})
            continue

        write_json(paths.results_raw_api / f"{submission_id}.stage1.response.json", response_body)
        parsed_by_submission[submission_id] = {
            "stage1_parsed": parsed,
            "stage1_parse_meta": parse_meta,
            "stage1_raw_text_chars": len(raw_text),
        }

    write_json(run_dir(paths, state["run_id"]) / "stage1.parsed.json", parsed_by_submission)
    write_json(run_dir(paths, state["run_id"]) / "stage1.processing_errors.json", errors)

    if errors and not args.continue_on_error:
        raise RuntimeError(f"Stage 1 had {len(errors)} processing errors. Use --continue-on-error to proceed.")

    state["stage1"].update(
        {
            "processed_at": utc_timestamp(),
            "processed_count": len(parsed_by_submission),
            "processing_error_count": len(errors),
            "successful_submissions": sorted(parsed_by_submission),
        }
    )
    state["status"] = "stage1_completed"
    state["updated_at"] = utc_timestamp()
    save_state(paths, state)
    print(f"Stage 1 processed: {len(parsed_by_submission)} ok, {len(errors)} errors")
    return state


def submit_stage2_batch(
    api_key: str,
    args: argparse.Namespace,
    paths: ExperimentPaths,
    state: dict,
) -> dict:
    if state["stage2"].get("batch_name"):
        return state

    parsed_path = run_dir(paths, state["run_id"]) / "stage1.parsed.json"
    parsed_by_submission = load_json(parsed_path)
    if not parsed_by_submission:
        raise RuntimeError("No successful Stage 1 outputs are available for Stage 2.")

    gemini_requests = []
    submission_ids = []
    for submission in state["submissions"]:
        submission_id = submission["submission_id"]
        stage1_payload = parsed_by_submission.get(submission_id)
        if not stage1_payload:
            continue
        prompt2_template = Path(submission["prompt2_path"]).read_text(encoding="utf-8")
        stage1_json = json.dumps(stage1_payload["stage1_parsed"], ensure_ascii=False, indent=2)
        prompt2_text = prompt2_template.replace("{{STAGE1_JSON}}", stage1_json)
        gemini_requests.append(
            build_gemini_batch_inline_request(
                prompt2_text,
                temperature=state["temperature"],
                reasoning_effort=state.get("reasoning_effort"),
                metadata={"submission_id": submission_id, "stage": "stage2"},
            )
        )
        submission_ids.append(submission_id)

    current_run_dir = run_dir(paths, state["run_id"])
    write_json(current_run_dir / "stage2.input.json", gemini_requests)
    state["stage2"]["submission_ids"] = submission_ids
    state["stage2"]["request_count"] = len(gemini_requests)

    if args.dry_run:
        state["stage2"]["dry_run_at"] = utc_timestamp()
        state["updated_at"] = utc_timestamp()
        save_state(paths, state)
        print(f"Stage 2 batch input written to {current_run_dir / 'stage2.input.json'}")
        print("Dry-run only; no Stage 2 Gemini batch was submitted.")
        return state

    client = gemini_client(api_key)
    batch_job = create_gemini_batch(
        client,
        state["model"],
        gemini_requests,
        display_name=f"{state['run_id']}-stage2",
    )
    write_json(current_run_dir / "stage2.batch.json", {"name": batch_job.name, "state": str(batch_job.state)})

    state["stage2"].update(
        {
            "batch_name": batch_job.name,
            "batch_status": batch_job.state.name,
            "submitted_at": utc_timestamp(),
        }
    )
    state["status"] = "stage2_submitted"
    state["updated_at"] = utc_timestamp()
    save_state(paths, state)
    print(f"Stage 2 Gemini batch submitted: {batch_job.name} ({batch_job.state.name})")
    return state


def finalize_stage2_outputs(
    config: dict,
    args: argparse.Namespace,
    paths: ExperimentPaths,
    state: dict,
    job,
) -> dict:
    if state["stage2"].get("finalized_at"):
        return state

    responses = collect_gemini_batch_responses(job)
    submission_ids = state["stage2"].get("submission_ids", [])
    if len(responses) != len(submission_ids):
        raise RuntimeError(
            f"Stage 2 response count mismatch: expected {len(submission_ids)}, got {len(responses)}"
        )

    stage1_by_submission = load_json(run_dir(paths, state["run_id"]) / "stage1.parsed.json")
    rubric = load_json(paths.rubric)
    errors = []
    saved_count = 0

    for submission_id, response in zip(submission_ids, responses):
        stage1_payload = stage1_by_submission.get(submission_id)
        if not stage1_payload:
            continue
        try:
            stage2_response_body = response_to_dict(response)
            stage2_text = extract_gemini_response_text(response)
            stage2_parsed, stage2_parse_meta = robust_json_loads(stage2_text)
        except Exception as error:
            errors.append({"submission_id": submission_id, "error": str(error)})
            continue

        submission = next(item for item in state["submissions"] if item["submission_id"] == submission_id)
        prompt1_text = Path(submission["prompt1_path"]).read_text(encoding="utf-8")
        prompt2_template = Path(submission["prompt2_path"]).read_text(encoding="utf-8")
        write_json(paths.results_raw_api / f"{submission_id}.stage2.response.json", stage2_response_body)
        write_json(
            paths.results_raw_api / f"{submission_id}.request.json",
            build_request_metadata(paths, state, submission, prompt1_text, prompt2_template),
        )

        stage1_parsed = stage1_payload["stage1_parsed"]
        parse_audit = {
            "stage1": stage1_payload["stage1_parse_meta"],
            "stage2": stage2_parse_meta,
            "stage1_raw_text_chars": stage1_payload["stage1_raw_text_chars"],
            "stage2_raw_text_chars": len(stage2_text),
        }
        write_json(
            paths.results_raw_parsed / f"{submission_id}.two_stage.parsed.json",
            {
                "submission_id": submission_id,
                "stage1_parsed": stage1_parsed,
                "stage2_parsed": stage2_parsed,
                "parse_audit": parse_audit,
            },
        )

        normalized_criteria, force_zero = normalize_llm_payload_stage1(
            stage1_parsed,
            submission_id,
            rubric,
            paths,
        )
        feedback_items = normalize_feedback_items(
            stage2_parsed.get("feedback_items", []),
            normalized_criteria,
            force_zero,
        )
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
            "confidence": normalize_confidence(
                stage1_parsed.get("confidence"),
                config["confidence_labels"],
            ),
        }
        write_json(paths.results_llm / f"{submission_id}.json", normalized_output)
        write_json(paths.results_normalized / f"{submission_id}.normalized.json", normalized_output)
        saved_count += 1

    write_json(run_dir(paths, state["run_id"]) / "stage2.processing_errors.json", errors)

    if errors and not args.continue_on_error:
        raise RuntimeError(f"Stage 2 had {len(errors)} processing errors. Use --continue-on-error to proceed.")

    state["stage2"].update(
        {
            "finalized_at": utc_timestamp(),
            "saved_count": saved_count,
            "processing_error_count": len(errors),
        }
    )
    state["status"] = "completed"
    state["updated_at"] = utc_timestamp()
    save_state(paths, state)
    print(f"Stage 2 finalized: {saved_count} outputs saved, {len(errors)} errors")
    return state


def wait_for_batch(api_key: str, batch_name: str, args: argparse.Namespace):
    client = gemini_client(api_key)
    started = time.monotonic()
    while True:
        job = retrieve_gemini_batch(client, batch_name)
        if job.state.name in GEMINI_TERMINAL_BATCH_STATUSES:
            return job
        if args.max_wait_seconds > 0 and time.monotonic() - started >= args.max_wait_seconds:
            raise RuntimeError(f"Max wait reached while polling batch {batch_name}")
        time.sleep(args.poll_seconds)


def advance_once(api_key: str, config: dict, args: argparse.Namespace, paths: ExperimentPaths, state: dict) -> dict:
    if state["status"] == "dry_run":
        return state

    if not state["stage1"].get("batch_name"):
        return submit_stage1_batch(api_key, config, args, paths)

    state, job = refresh_stage_batch(api_key, args, paths, state, "stage1")
    stage1_status = state["stage1"].get("batch_status")
    if stage1_status not in GEMINI_TERMINAL_BATCH_STATUSES:
        return state
    if stage1_status != "JOB_STATE_SUCCEEDED":
        state["status"] = "failed"
        state["updated_at"] = utc_timestamp()
        save_state(paths, state)
        return state

    state = process_stage1_outputs(api_key, args, paths, state, job)
    if not state["stage2"].get("batch_name"):
        return submit_stage2_batch(api_key, args, paths, state)

    state, job = refresh_stage_batch(api_key, args, paths, state, "stage2")
    stage2_status = state["stage2"].get("batch_status")
    if stage2_status not in GEMINI_TERMINAL_BATCH_STATUSES:
        return state
    if stage2_status != "JOB_STATE_SUCCEEDED":
        state["status"] = "failed"
        state["updated_at"] = utc_timestamp()
        save_state(paths, state)
        return state

    return finalize_stage2_outputs(config, args, paths, state, job)


def print_status(state: dict) -> None:
    print(f"Run: {state['run_id']}")
    print(f"Status: {state.get('status')}")
    print(f"Model: {state.get('model')}")
    print(f"Submissions: {len(state.get('submissions', []))}")
    for stage in ("stage1", "stage2"):
        stage_state = state.get(stage, {})
        batch_name = stage_state.get("batch_name")
        batch_status = stage_state.get("batch_status")
        if batch_name or batch_status:
            print(f"{stage}: {batch_name or '-'} ({batch_status or '-'})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Executes two-stage Gemini evaluations using the Batch API.")
    add_experiment_argument(parser)
    parser.add_argument(
        "--submission-id",
        action="append",
        help="Can be repeated to limit execution to specific submissions.",
    )
    parser.add_argument("--limit", type=int, help="Limits the number of executed prompts.")
    parser.add_argument("--model", help="Overrides the model from config.")
    parser.add_argument("--temperature", type=float, help="Generation temperature.")
    parser.add_argument(
        "--reasoning-effort",
        choices=["minimal", "low", "medium", "high", "xhigh", "balanced"],
        help="Reasoning effort for Gemini models that support it.",
    )
    parser.add_argument("--env-file", default=".env", help="Environment file relative to the repository root.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrites existing results.")
    parser.add_argument("--dry-run", action="store_true", help="Builds batch files without calling the API.")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continues to the next stage/output when individual requests fail.",
    )
    parser.add_argument(
        "--action",
        choices=["start", "advance", "status"],
        default="advance",
        help="start creates a new Stage 1 batch; advance polls and moves the run forward.",
    )
    parser.add_argument("--run-id", help="Batch run id to resume. Defaults to latest run for advance/status.")
    parser.add_argument("--timeout-seconds", type=int, default=180, help="Reserved for future file-based batch support.")
    parser.add_argument("--wait", action="store_true", help="Poll until the two-stage run completes or max wait is reached.")
    parser.add_argument("--poll-seconds", type=float, default=60.0, help="Polling interval used with --wait.")
    parser.add_argument(
        "--max-wait-seconds",
        type=float,
        default=0.0,
        help="Maximum wait time with --wait. Use 0 for no maximum.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = ExperimentPaths(args.experiment)
    config = load_json(paths.experiment_config)
    provider = config["llm_protocol"]["provider"]
    if provider != "gemini":
        raise SystemExit("Gemini Batch execution requires llm_protocol.provider=gemini.")

    env_file = (EXPERIMENT_ROOT / args.env_file).resolve()
    api_key = get_gemini_api_key(env_file)
    if not api_key and not args.dry_run:
        raise SystemExit("GEMINI_API_KEY not found. Set it in .env or the shell environment.")

    if args.action == "start":
        state = submit_stage1_batch(api_key or "", config, args, paths)
    else:
        run_id = args.run_id or resolve_latest_run_id(paths)
        if not run_id:
            if args.action == "status":
                raise SystemExit("No latest Gemini grading batch run found.")
            state = submit_stage1_batch(api_key or "", config, args, paths)
        else:
            state = load_state(paths, run_id)

    if args.action == "status":
        print_status(state)
        return

    started = time.monotonic()
    while True:
        if not api_key and not args.dry_run:
            raise SystemExit("GEMINI_API_KEY not found.")

        state = advance_once(api_key, config, args, paths, state)
        if state.get("status") in {"completed", "failed", "dry_run"}:
            print_status(state)
            return

        if not args.wait:
            print_status(state)
            return
        if args.max_wait_seconds > 0 and time.monotonic() - started >= args.max_wait_seconds:
            print("Max wait reached; run can be resumed later with --action advance.")
            print_status(state)
            return
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
