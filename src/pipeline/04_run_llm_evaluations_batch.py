#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, add_experiment_argument
from pipeline.utils.llm_execution import (
    build_openai_responses_payload,
    extract_openai_text,
    robust_json_loads,
)
from pipeline.utils.normalizers import (
    build_student_feedback,
    normalize_confidence,
    normalize_feedback_items,
    normalize_llm_payload_stage1,
    prompt_hash,
    weighted_total_score,
)


EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
OPENAI_BASE_URL = "https://api.openai.com"
BATCH_ENDPOINT = "/v1/responses"
TERMINAL_BATCH_STATUSES = {"completed", "failed", "cancelled", "expired"}


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


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise RuntimeError(f"Invalid JSONL at {path}:{line_number}: {error}") from error
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, separators=(",", ":")))
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


def get_openai_api_key(env_file: Path) -> str | None:
    env_values = load_dotenv(env_file)
    return os.environ.get("OPENAI_API_KEY") or env_values.get("OPENAI_API_KEY")


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


def openai_json_request(
    api_key: str,
    method: str,
    path: str,
    payload: dict | None = None,
    timeout_seconds: int = 120,
) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    request = Request(
        f"{OPENAI_BASE_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw_bytes = response.read()
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"OpenAI API error {error.code} on {method} {path}: {error_body}"
        ) from error
    except URLError as error:
        raise RuntimeError(f"OpenAI API connection error on {method} {path}: {error}") from error
    return json.loads(raw_bytes.decode("utf-8"))


def openai_upload_batch_file(api_key: str, file_path: Path, timeout_seconds: int) -> dict:
    boundary = f"codex-{uuid.uuid4().hex}"
    file_bytes = file_path.read_bytes()
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        b'Content-Disposition: form-data; name="purpose"\r\n\r\n',
        b"batch\r\n",
        f"--{boundary}\r\n".encode("utf-8"),
        (
            'Content-Disposition: form-data; name="file"; '
            f'filename="{file_path.name}"\r\n'
        ).encode("utf-8"),
        b"Content-Type: application/jsonl\r\n\r\n",
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    body = b"".join(parts)
    request = Request(
        f"{OPENAI_BASE_URL}/v1/files",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw_bytes = response.read()
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI file upload error {error.code}: {error_body}") from error
    except URLError as error:
        raise RuntimeError(f"OpenAI file upload connection error: {error}") from error
    return json.loads(raw_bytes.decode("utf-8"))


def openai_download_file(api_key: str, file_id: str, timeout_seconds: int) -> bytes:
    request = Request(
        f"{OPENAI_BASE_URL}/v1/files/{file_id}/content",
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read()
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI file download error {error.code}: {error_body}") from error
    except URLError as error:
        raise RuntimeError(f"OpenAI file download connection error: {error}") from error


def create_openai_batch(
    api_key: str,
    input_file_id: str,
    completion_window: str,
    metadata: dict[str, str],
    timeout_seconds: int,
) -> dict:
    payload = {
        "input_file_id": input_file_id,
        "endpoint": BATCH_ENDPOINT,
        "completion_window": completion_window,
        "metadata": metadata,
    }
    return openai_json_request(api_key, "POST", "/v1/batches", payload, timeout_seconds)


def retrieve_openai_batch(api_key: str, batch_id: str, timeout_seconds: int) -> dict:
    return openai_json_request(api_key, "GET", f"/v1/batches/{batch_id}", timeout_seconds=timeout_seconds)


def stage_custom_id(submission_id: str, stage: str) -> str:
    return f"{submission_id}:{stage}"


def response_body_from_batch_row(row: dict) -> dict:
    response = row.get("response")
    if not response:
        raise RuntimeError(f"Batch row has no response: {row}")
    status_code = response.get("status_code")
    if status_code != 200:
        raise RuntimeError(f"Batch request failed with status {status_code}: {response.get('body')}")
    body = response.get("body")
    if not isinstance(body, dict):
        raise RuntimeError(f"Batch row response body is not a JSON object: {row}")
    if body.get("status") == "incomplete":
        raise RuntimeError(f"Incomplete OpenAI response: {body.get('incomplete_details')}")
    if body.get("error"):
        raise RuntimeError(f"OpenAI response error: {body.get('error')}")
    return body


def batch_rows_by_custom_id(output_path: Path) -> dict[str, dict]:
    return {row.get("custom_id"): row for row in read_jsonl(output_path)}


def select_submissions(config: dict, args: argparse.Namespace, paths: ExperimentPaths) -> list[dict]:
    prompt_dir = paths.rendered_prompts_dir
    if not prompt_dir.exists():
        raise SystemExit(f"Prompt directory not found: {prompt_dir}")

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
        "execution_mode": "openai_batch",
        "provider": "openai",
        "model": state["model"],
        "temperature": state["temperature"],
        "reasoning_effort": state.get("reasoning_effort"),
        "batch_run_id": state["run_id"],
        "stage1_batch_id": state.get("stage1", {}).get("batch_id"),
        "stage2_batch_id": state.get("stage2", {}).get("batch_id"),
        "stage1_custom_id": stage_custom_id(submission["submission_id"], "stage1"),
        "stage2_custom_id": stage_custom_id(submission["submission_id"], "stage2"),
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


def make_batch_request(custom_id: str, body: dict) -> dict:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": BATCH_ENDPOINT,
        "body": body,
    }


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

    run_id = args.run_id or f"{paths.experiment_name}-{utc_timestamp()}"
    state = {
        "run_id": run_id,
        "status": "created",
        "experiment": paths.experiment_name,
        "created_at": utc_timestamp(),
        "updated_at": utc_timestamp(),
        "provider": "openai",
        "model": model,
        "temperature": temperature,
        "reasoning_effort": reasoning_effort,
        "max_output_tokens": args.max_output_tokens,
        "completion_window": args.completion_window,
        "submissions": select_submissions(config, args, paths),
        "stage1": {},
        "stage2": {},
    }

    rows = []
    for submission in state["submissions"]:
        submission_id = submission["submission_id"]
        prompt_text = Path(submission["prompt1_path"]).read_text(encoding="utf-8")
        body = build_openai_responses_payload(
            model,
            prompt_text,
            temperature,
            reasoning_effort=reasoning_effort,
            max_output_tokens=args.max_output_tokens,
        )
        rows.append(make_batch_request(stage_custom_id(submission_id, "stage1"), body))

    current_run_dir = run_dir(paths, run_id)
    input_path = current_run_dir / "stage1.input.jsonl"
    write_jsonl(input_path, rows)
    state["stage1"]["input_path"] = str(input_path)
    state["stage1"]["request_count"] = len(rows)

    print(f"Experiment: {paths.experiment_name}")
    print(f"Provider: openai")
    print(f"Model: {model} (Two-Stage Batch Execution)")
    if reasoning_effort:
        print(f"Reasoning effort: {reasoning_effort}")
    print(f"Selected prompts: {len(rows)}")
    print(f"Batch run: {run_id}")

    if args.dry_run:
        state["status"] = "dry_run"
        state["updated_at"] = utc_timestamp()
        save_state(paths, state)
        print(f"Stage 1 batch input written to {input_path}")
        print("Dry-run only; no OpenAI request was submitted.")
        return state

    uploaded_file = openai_upload_batch_file(api_key, input_path, args.timeout_seconds)
    write_json(current_run_dir / "stage1.file.json", uploaded_file)
    batch = create_openai_batch(
        api_key,
        uploaded_file["id"],
        args.completion_window,
        {
            "experiment": paths.experiment_name,
            "run_id": run_id,
            "stage": "stage1",
            "model": model,
        },
        args.timeout_seconds,
    )
    write_json(current_run_dir / "stage1.batch.json", batch)

    state["stage1"].update(
        {
            "input_file_id": uploaded_file["id"],
            "batch_id": batch["id"],
            "batch_status": batch["status"],
            "submitted_at": utc_timestamp(),
        }
    )
    state["status"] = "stage1_submitted"
    state["updated_at"] = utc_timestamp()
    save_state(paths, state)
    print(f"Stage 1 batch submitted: {batch['id']} ({batch['status']})")
    return state


def refresh_batch_status(
    api_key: str,
    args: argparse.Namespace,
    paths: ExperimentPaths,
    state: dict,
    stage: str,
) -> dict:
    stage_state = state[stage]
    batch_id = stage_state.get("batch_id")
    if not batch_id:
        return state

    batch = retrieve_openai_batch(api_key, batch_id, args.timeout_seconds)
    write_json(run_dir(paths, state["run_id"]) / f"{stage}.batch.json", batch)
    stage_state.update(
        {
            "batch_status": batch.get("status"),
            "output_file_id": batch.get("output_file_id"),
            "error_file_id": batch.get("error_file_id"),
            "request_counts": batch.get("request_counts"),
            "last_checked_at": utc_timestamp(),
        }
    )
    state["updated_at"] = utc_timestamp()
    save_state(paths, state)
    print(f"{stage}: batch {batch_id} is {batch.get('status')}")
    return state


def download_stage_outputs(
    api_key: str,
    args: argparse.Namespace,
    paths: ExperimentPaths,
    state: dict,
    stage: str,
) -> tuple[Path | None, Path | None]:
    current_run_dir = run_dir(paths, state["run_id"])
    stage_state = state[stage]
    output_path = None
    error_path = None

    output_file_id = stage_state.get("output_file_id")
    if output_file_id:
        output_path = current_run_dir / f"{stage}.output.jsonl"
        if not output_path.exists() or args.overwrite:
            output_path.write_bytes(openai_download_file(api_key, output_file_id, args.timeout_seconds))
        stage_state["output_path"] = str(output_path)

    error_file_id = stage_state.get("error_file_id")
    if error_file_id:
        error_path = current_run_dir / f"{stage}.errors.jsonl"
        if not error_path.exists() or args.overwrite:
            error_path.write_bytes(openai_download_file(api_key, error_file_id, args.timeout_seconds))
        stage_state["error_path"] = str(error_path)

    state["updated_at"] = utc_timestamp()
    save_state(paths, state)
    return output_path, error_path


def process_stage1_outputs(
    api_key: str,
    args: argparse.Namespace,
    paths: ExperimentPaths,
    state: dict,
) -> dict:
    if state["stage1"].get("processed_at"):
        return state

    output_path, _ = download_stage_outputs(api_key, args, paths, state, "stage1")
    if output_path is None:
        raise RuntimeError("Stage 1 completed without an output file.")

    rows = batch_rows_by_custom_id(output_path)
    parsed_by_submission = {}
    errors = []

    for submission in state["submissions"]:
        submission_id = submission["submission_id"]
        custom_id = stage_custom_id(submission_id, "stage1")
        row = rows.get(custom_id)
        if not row:
            errors.append({"submission_id": submission_id, "error": "missing stage1 batch row"})
            continue
        if row.get("error"):
            errors.append({"submission_id": submission_id, "error": row["error"]})
            continue
        try:
            response_body = response_body_from_batch_row(row)
            raw_text = extract_openai_text(response_body)
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
    if state["stage2"].get("batch_id"):
        return state

    parsed_path = run_dir(paths, state["run_id"]) / "stage1.parsed.json"
    parsed_by_submission = load_json(parsed_path)
    if not parsed_by_submission:
        raise RuntimeError("No successful Stage 1 outputs are available for Stage 2.")

    rows = []
    for submission in state["submissions"]:
        submission_id = submission["submission_id"]
        stage1_payload = parsed_by_submission.get(submission_id)
        if not stage1_payload:
            continue
        prompt2_template = Path(submission["prompt2_path"]).read_text(encoding="utf-8")
        stage1_json = json.dumps(stage1_payload["stage1_parsed"], ensure_ascii=False, indent=2)
        prompt2_text = prompt2_template.replace("{{STAGE1_JSON}}", stage1_json)
        body = build_openai_responses_payload(
            state["model"],
            prompt2_text,
            state["temperature"],
            reasoning_effort=state.get("reasoning_effort"),
            max_output_tokens=state.get("max_output_tokens", args.max_output_tokens),
        )
        rows.append(make_batch_request(stage_custom_id(submission_id, "stage2"), body))

    input_path = run_dir(paths, state["run_id"]) / "stage2.input.jsonl"
    write_jsonl(input_path, rows)
    state["stage2"]["input_path"] = str(input_path)
    state["stage2"]["request_count"] = len(rows)

    if args.dry_run:
        state["stage2"]["dry_run_at"] = utc_timestamp()
        state["updated_at"] = utc_timestamp()
        save_state(paths, state)
        print(f"Stage 2 batch input written to {input_path}")
        print("Dry-run only; no Stage 2 OpenAI request was submitted.")
        return state

    uploaded_file = openai_upload_batch_file(api_key, input_path, args.timeout_seconds)
    write_json(run_dir(paths, state["run_id"]) / "stage2.file.json", uploaded_file)
    batch = create_openai_batch(
        api_key,
        uploaded_file["id"],
        state["completion_window"],
        {
            "experiment": paths.experiment_name,
            "run_id": state["run_id"],
            "stage": "stage2",
            "model": state["model"],
        },
        args.timeout_seconds,
    )
    write_json(run_dir(paths, state["run_id"]) / "stage2.batch.json", batch)

    state["stage2"].update(
        {
            "input_file_id": uploaded_file["id"],
            "batch_id": batch["id"],
            "batch_status": batch["status"],
            "submitted_at": utc_timestamp(),
        }
    )
    state["status"] = "stage2_submitted"
    state["updated_at"] = utc_timestamp()
    save_state(paths, state)
    print(f"Stage 2 batch submitted: {batch['id']} ({batch['status']})")
    return state


def finalize_stage2_outputs(
    api_key: str,
    config: dict,
    args: argparse.Namespace,
    paths: ExperimentPaths,
    state: dict,
) -> dict:
    if state["stage2"].get("finalized_at"):
        return state

    output_path, _ = download_stage_outputs(api_key, args, paths, state, "stage2")
    if output_path is None:
        raise RuntimeError("Stage 2 completed without an output file.")

    stage1_by_submission = load_json(run_dir(paths, state["run_id"]) / "stage1.parsed.json")
    stage2_rows = batch_rows_by_custom_id(output_path)
    rubric = load_json(paths.rubric)
    errors = []
    saved_count = 0

    for submission in state["submissions"]:
        submission_id = submission["submission_id"]
        stage1_payload = stage1_by_submission.get(submission_id)
        if not stage1_payload:
            continue
        row = stage2_rows.get(stage_custom_id(submission_id, "stage2"))
        if not row:
            errors.append({"submission_id": submission_id, "error": "missing stage2 batch row"})
            continue
        if row.get("error"):
            errors.append({"submission_id": submission_id, "error": row["error"]})
            continue

        try:
            stage2_response_body = response_body_from_batch_row(row)
            stage2_text = extract_openai_text(stage2_response_body)
            stage2_parsed, stage2_parse_meta = robust_json_loads(stage2_text)
        except Exception as error:
            errors.append({"submission_id": submission_id, "error": str(error)})
            continue

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


def advance_once(api_key: str, config: dict, args: argparse.Namespace, paths: ExperimentPaths, state: dict) -> dict:
    if state["status"] == "dry_run":
        return state

    if not state["stage1"].get("batch_id"):
        return submit_stage1_batch(api_key, config, args, paths)

    state = refresh_batch_status(api_key, args, paths, state, "stage1")
    stage1_status = state["stage1"].get("batch_status")
    if stage1_status not in TERMINAL_BATCH_STATUSES:
        return state
    if stage1_status != "completed":
        state["status"] = "failed"
        state["updated_at"] = utc_timestamp()
        save_state(paths, state)
        return state

    state = process_stage1_outputs(api_key, args, paths, state)
    if not state["stage2"].get("batch_id"):
        state = submit_stage2_batch(api_key, args, paths, state)
        return state

    state = refresh_batch_status(api_key, args, paths, state, "stage2")
    stage2_status = state["stage2"].get("batch_status")
    if stage2_status not in TERMINAL_BATCH_STATUSES:
        return state
    if stage2_status != "completed":
        state["status"] = "failed"
        state["updated_at"] = utc_timestamp()
        save_state(paths, state)
        return state

    return finalize_stage2_outputs(api_key, config, args, paths, state)


def print_status(state: dict) -> None:
    print(f"Run: {state['run_id']}")
    print(f"Status: {state.get('status')}")
    print(f"Model: {state.get('model')}")
    print(f"Submissions: {len(state.get('submissions', []))}")
    for stage in ("stage1", "stage2"):
        stage_state = state.get(stage, {})
        batch_id = stage_state.get("batch_id")
        batch_status = stage_state.get("batch_status")
        if batch_id or batch_status:
            print(f"{stage}: {batch_id or '-'} ({batch_status or '-'})")
        if stage_state.get("request_counts"):
            print(f"{stage} request counts: {stage_state['request_counts']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Executes two-stage OpenAI evaluations using the Batch API.")
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
        choices=["minimal", "low", "medium", "high", "xhigh"],
        help="Reasoning effort for OpenAI models that support it.",
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
    parser.add_argument("--completion-window", default="24h", help="Batch completion window; OpenAI currently supports 24h.")
    parser.add_argument("--timeout-seconds", type=int, default=180, help="Timeout for OpenAI control-plane requests.")
    parser.add_argument("--max-output-tokens", type=int, default=20000, help="Maximum output tokens per Responses API request.")
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
    if provider != "openai":
        raise SystemExit("OpenAI Batch execution requires llm_protocol.provider=openai.")

    env_file = (EXPERIMENT_ROOT / args.env_file).resolve()
    api_key = get_openai_api_key(env_file)
    if not api_key and not args.dry_run:
        raise SystemExit("OPENAI_API_KEY not found. Set it in .env or the shell environment.")

    if args.action == "start":
        state = submit_stage1_batch(api_key or "", config, args, paths)
    else:
        run_id = args.run_id or resolve_latest_run_id(paths)
        if not run_id:
            if args.action == "status":
                raise SystemExit("No latest batch run found.")
            state = submit_stage1_batch(api_key or "", config, args, paths)
        else:
            state = load_state(paths, run_id)
            if args.action == "status":
                if api_key and state.get("status") not in {"completed", "failed", "dry_run"}:
                    if state.get("stage1", {}).get("batch_id"):
                        state = refresh_batch_status(api_key, args, paths, state, "stage1")
                    if state.get("stage2", {}).get("batch_id"):
                        state = refresh_batch_status(api_key, args, paths, state, "stage2")
                print_status(state)
                return

    started = time.monotonic()
    while args.action != "start":
        previous_status = state.get("status")
        state = advance_once(api_key or "", config, args, paths, state)
        if state.get("status") in {"completed", "failed", "dry_run"}:
            break
        if not args.wait:
            break
        if args.max_wait_seconds > 0 and time.monotonic() - started >= args.max_wait_seconds:
            print("Max wait reached; run can be resumed later with --action advance.")
            break
        if state.get("status") == previous_status:
            time.sleep(args.poll_seconds)

    print_status(state)


if __name__ == "__main__":
    main()
