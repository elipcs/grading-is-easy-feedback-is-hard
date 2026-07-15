#!/usr/bin/env python3
"""
Classify feedback problems (from both human and LLM evaluations)
into a unified semantic taxonomy using an LLM API.
"""

import json
import os
import sys
import time
import uuid
import concurrent.futures
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, add_experiment_argument
from pipeline.utils.llm_execution import (
    build_openai_responses_payload,
    call_anthropic,
    extract_anthropic_text,
    extract_openai_text,
    supports_anthropic_temperature,
    robust_json_loads,
)
import argparse
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

EXPERIMENT_ROOT = Path(__file__).resolve().parents[2]
OPENAI_BASE_URL = "https://api.openai.com"
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
ANTHROPIC_BASE_URL = "https://api.anthropic.com"
OPENAI_BATCH_ENDPOINT = "/v1/responses"
TERMINAL_BATCH_STATUSES = {"completed", "failed", "cancelled", "expired"}
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"
GEMINI_TERMINAL_BATCH_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"}
ANTHROPIC_TERMINAL_BATCH_STATUSES = {"ended", "canceling"}

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-sonnet-5"

DEFAULT_MODELS = {
    "gemini": {
        "taxonomy": "gemini-3-flash-preview",
        "semantic": "gemini-3.1-flash-lite-preview",
    },
    "openai": {
        "taxonomy": "gpt-5.5",
        "semantic": "gpt-5.5",
    },
    "anthropic": {
        "taxonomy": "claude-sonnet-5",
        "semantic": "claude-sonnet-5",
    },
}

TAXONOMY_PROMPT = """
You are a Computer Science evaluator analyzing feedback given to students in a Java programming lab.
Your task is to classify student feedback "problems" into one or more of the following taxonomy categories.

Taxonomy:
- list_validation: validation of HotList position, existence of item, or invalid input limits.
- string_comparison: using `==` instead of `.equals()` to compare strings.
- hashcode_equals: consistency between `hashCode()` and `equals()` methods.
- tests_missing: missing, incomplete or weak JUnit tests.
- class_modeling: wrong placement of logic (e.g. state in Filme instead of FilmNow), static methods that should be instance methods, classes ignoring their main purpose.
- reference_usage: storing strings text instead of Object references, breaking composition principles.
- array_usage: incorrect array size, arrays not initialized in constructor.
- responsibility_division: Main class handling business logic, reading input or printing when it shouldn't, accessing internal domain objects instead of relying on the controller.
- readability_docs: variable names, missing Javadoc, poorly readable code structure.
- input_handling: `Scanner` using `next()` instead of `nextLine()`.
- output_format: wrong output string format, missing formatting like the '🔥' emoji.
- other: if it truly fits none of the above.

Respond ONLY with a valid JSON RECORD (object) mapping each EXACT problem text to its list of assigned categories.
IMPORTANT: If a problem description contains multiple distinct issues (e.g. both a validation bug and a documentation issue), you MUST list ALL relevant categories.

Example:
{
  "problem 1 text...": ["list_validation", "class_modeling"],
  "problem 2 text...": ["input_handling"]
}
Do not include markdown wrappers. Ensure the keys match the input strings exactly.

Feedback Problems to classify:
{problems_json}
"""
""

def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def load_dotenv(path):
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

def get_openai_api_key():
    env_values = load_dotenv(EXPERIMENT_ROOT / ".env")
    return os.environ.get("OPENAI_API_KEY") or env_values.get("OPENAI_API_KEY")

def get_gemini_api_key():
    env_values = load_dotenv(EXPERIMENT_ROOT / ".env")
    return (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or env_values.get("GEMINI_API_KEY")
        or env_values.get("GOOGLE_API_KEY")
    )

def get_anthropic_api_key():
    env_values = load_dotenv(EXPERIMENT_ROOT / ".env")
    return (
        os.environ.get("ANTHROPIC_API_KEY")
        or env_values.get("ANTHROPIC_API_KEY")
    )

def get_api_key_for_provider(provider):
    if provider == "openai":
        return get_openai_api_key()
    if provider == "anthropic":
        return get_anthropic_api_key()
    return get_gemini_api_key()

def resolve_provider_model(provider, model, role="semantic"):
    defaults = DEFAULT_MODELS.get(provider, DEFAULT_MODELS[DEFAULT_PROVIDER])
    if model in {None, "", DEFAULT_MODEL, "gemini-3.1-pro-preview", "gemini-3.1-flash-lite-preview"}:
        return defaults[role]
    return model

def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

def read_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise RuntimeError(f"Invalid JSONL at {path}:{line_number}: {error}") from error
    return rows

def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True, separators=(",", ":")))
            f.write("\n")

def openai_json_request(api_key, method, path, payload=None, timeout_seconds=120, base_url=OPENAI_BASE_URL):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{base_url}{path}",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error {error.code} on {method} {path}: {error_body}") from error
    except URLError as error:
        raise RuntimeError(f"OpenAI API connection error on {method} {path}: {error}") from error

def openai_upload_batch_file(api_key, file_path, timeout_seconds, base_url=OPENAI_BASE_URL):
    boundary = f"codex-{uuid.uuid4().hex}"
    file_bytes = file_path.read_bytes()
    body = b"".join([
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
    ])
    request = Request(
        f"{base_url}/v1/files",
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
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI file upload error {error.code}: {error_body}") from error
    except URLError as error:
        raise RuntimeError(f"OpenAI file upload connection error: {error}") from error

def openai_download_file(api_key, file_id, timeout_seconds, base_url=OPENAI_BASE_URL):
    request = Request(
        f"{base_url}/v1/files/{file_id}/content",
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

def create_openai_batch(api_key, input_file_id, completion_window, metadata, timeout_seconds, base_url=OPENAI_BASE_URL):
    return openai_json_request(
        api_key,
        "POST",
        "/v1/batches",
        {
            "input_file_id": input_file_id,
            "endpoint": OPENAI_BATCH_ENDPOINT,
            "completion_window": completion_window,
            "metadata": metadata,
        },
        timeout_seconds,
        base_url=base_url
    )

def retrieve_openai_batch(api_key, batch_id, timeout_seconds, base_url=OPENAI_BASE_URL):
    return openai_json_request(api_key, "GET", f"/v1/batches/{batch_id}", timeout_seconds=timeout_seconds, base_url=base_url)

def classification_runs_dir(paths):
    return paths.results_analysis / "classification_batch_runs"

def classification_run_dir(paths, run_id):
    return classification_runs_dir(paths) / run_id

def classification_state_path(paths, run_id):
    return classification_run_dir(paths, run_id) / "state.json"

def latest_classification_run_path(paths):
    return classification_runs_dir(paths) / "latest_run.json"

def save_classification_state(paths, state):
    state["updated_at"] = utc_timestamp()
    write_json(classification_state_path(paths, state["run_id"]), state)
    write_json(latest_classification_run_path(paths), {"run_id": state["run_id"], "updated_at": state["updated_at"]})

def load_classification_state(paths, run_id):
    return json.loads(classification_state_path(paths, run_id).read_text(encoding="utf-8"))

def resolve_latest_classification_run_id(paths):
    marker = latest_classification_run_path(paths)
    if not marker.exists():
        return None
    return json.loads(marker.read_text(encoding="utf-8")).get("run_id")

def response_body_from_batch_row(row):
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

def gemini_json_request(api_key, method, path, payload=None, timeout_seconds=120):
    query = urlencode({"key": api_key})
    url = f"{GEMINI_BASE_URL}{path}?{query}"
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API error {error.code} on {method} {path}: {error_body}") from error
    except URLError as error:
        raise RuntimeError(f"Gemini API connection error on {method} {path}: {error}") from error

def gemini_upload_batch_file(api_key, file_path, timeout_seconds):
    query = urlencode({"key": api_key})
    url = f"{GEMINI_BASE_URL}/upload/v1beta/files?{query}"
    boundary = f"codex-{uuid.uuid4().hex}"
    file_bytes = file_path.read_bytes()
    
    # Gemini File API expects a specific multipart format
    metadata = json.dumps({"file": {"display_name": file_path.name}}).encode("utf-8")
    
    body = b"".join([
        f"--{boundary}\r\n".encode("utf-8"),
        b'Content-Type: application/json; charset=UTF-8\r\n\r\n',
        metadata,
        b"\r\n",
        f"--{boundary}\r\n".encode("utf-8"),
        f'Content-Type: application/jsonl\r\n\r\n'.encode("utf-8"),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ])
    
    request = Request(
        url,
        data=body,
        headers={
            "X-Goog-Upload-Protocol": "multipart",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini file upload error {error.code}: {error_body}") from error

def create_gemini_batch_sdk(api_key, model, requests_list):
    if genai is None:
        raise ImportError("google-genai package not installed.")
    
    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
    # Convert our requests to the format expected by the SDK
    # Our requests are already in GenerateContentRequest format
    
    # We'll use inline for simplicity since it's small
    batch_job = client.batches.create(
        model=model,
        src={'inlined_requests': requests_list},
        config={'display_name': f"semantic-match-{utc_timestamp()}"}
    )
    return batch_job

def retrieve_gemini_batch_sdk(api_key, batch_name):
    if genai is None:
        raise ImportError("google-genai package not installed.")
    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
    return client.batches.get(name=batch_name)

def gemini_download_file(api_key, file_name, timeout_seconds):
    query = urlencode({"key": api_key})
    # file_name is usually "files/XXXX"
    url = f"{GEMINI_BASE_URL}/v1beta/{file_name}/content?{query}"
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read()
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini file download error {error.code}: {error_body}") from error


def anthropic_json_request(api_key, method, path, payload=None, timeout_seconds=120):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{ANTHROPIC_BASE_URL}{path}",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic API error {error.code} on {method} {path}: {error_body}") from error
    except URLError as error:
        raise RuntimeError(f"Anthropic API connection error on {method} {path}: {error}") from error


def create_anthropic_message_batch(api_key, requests, timeout_seconds):
    return anthropic_json_request(
        api_key,
        "POST",
        "/v1/messages/batches",
        {"requests": requests},
        timeout_seconds=timeout_seconds,
    )


def retrieve_anthropic_message_batch(api_key, batch_id, timeout_seconds):
    return anthropic_json_request(
        api_key,
        "GET",
        f"/v1/messages/batches/{batch_id}",
        timeout_seconds=timeout_seconds,
    )


def download_anthropic_results(api_key, results_url, timeout_seconds):
    request = Request(
        results_url,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read()
    except HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic results download error {error.code}: {error_body}") from error
    except URLError as error:
        raise RuntimeError(f"Anthropic results download connection error: {error}") from error

SEMANTIC_MATCH_PROMPT = """
You are a Computer Science teaching assistant comparing feedback problems from two evaluators of the same student submission.

Your task: decide which expert problems are covered by LLM problems, and which LLM problems have no expert equivalent.

Rules for "Coverage":
- An expert problem is "covered" if at least one LLM problem describes the same root cause or same specific bug, even with different wording.
- SUBSUMPTION: If one description is more specific than the other, they still match if the core issue is the same.
- A single LLM problem can cover multiple expert problems, and vice-versa.

INPUT FORMAT:
A JSON object where each key is a criterion_id, and the value has:
- "expert": list of problem descriptions from the expert evaluator
- "llm": list of problem descriptions from the LLM evaluator

OUTPUT FORMAT:
A JSON object with the same criterion keys. For each criterion, output THREE lists:
- "covered_expert": expert problems that ARE covered by at least one LLM problem (TP from expert perspective)
- "uncovered_expert": expert problems NOT covered by any LLM problem (FN)
- "unmatched_llm": LLM problems that do NOT match any expert problem (FP)

IMPORTANT: Every expert problem must appear in exactly one of: covered_expert OR uncovered_expert.
IMPORTANT: Every LLM problem must appear in exactly one of: matched (implied by covered_expert) OR unmatched_llm.

Respond ONLY with the JSON object. No markdown, no explanation.

SUBMISSION CRITERIA TO COMPARE:
{criteria_json}
"""


def call_gemini_semantic_match(criteria_dict, api_key, model="gemini-3.1-flash-lite-preview", max_retries=15):
    """Ask Gemini to semantically match LLM problems against expert problems per criterion."""
    query = urlencode({"key": api_key})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?{query}"

    prompt = SEMANTIC_MATCH_PROMPT.replace(
        "{criteria_json}",
        json.dumps(criteria_dict, ensure_ascii=False, indent=2)
    )

    payload = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "systemInstruction": {
            "parts": [{"text": "Respond ONLY with a valid JSON object. No markdown."}]
        },
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
            "thinkingConfig": {
                "thinking_level": "high"
            }
        },
    }).encode("utf-8")

    request = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    
    for attempt in range(max_retries + 1):
        try:
            with urlopen(request, timeout=600) as response:
                result = json.loads(response.read().decode("utf-8"))
            parts = []
            for candidate in result.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if text := part.get("text"):
                        parts.append(text)
            clean_text = "".join(parts).strip()
            match = re.search(r'\{.*\}', clean_text, re.DOTALL)
            if match:
                clean_text = match.group(0)
            parsed = json.loads(clean_text)
            if isinstance(parsed, dict):
                return parsed
            return {}
        except HTTPError as e:
            if e.code in {429, 503} and attempt < max_retries:
                wait = 30
                print(f"  Rate limited ({e.code}), waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            print(f"ERROR: Gemini semantic match API returned {e.code}", file=sys.stderr)
            return {}
        except (json.JSONDecodeError, Exception) as e:
            print(f"ERROR: Semantic match failed: {e}", file=sys.stderr)
            return {}


def call_anthropic_semantic_match(criteria_dict, api_key, model="claude-sonnet-5", max_retries=15):
    """Ask Claude to semantically match LLM problems against expert problems per criterion."""
    prompt = SEMANTIC_MATCH_PROMPT.replace(
        "{criteria_json}",
        json.dumps(criteria_dict, ensure_ascii=False, indent=2)
    )

    for attempt in range(max_retries + 1):
        try:
            clean_text, _ = call_anthropic(
                api_key,
                model,
                prompt,
                temperature=0.0,
                timeout_seconds=600,
                system_prompt="Respond ONLY with a valid JSON object. No markdown.",
            )
            match = re.search(r'\{.*\}', clean_text, re.DOTALL)
            if match:
                clean_text = match.group(0)
            parsed = json.loads(clean_text)
            if isinstance(parsed, dict):
                return parsed
            return {}
        except HTTPError as e:
            if e.code in {429, 503, 529} and attempt < max_retries:
                wait = min(2 ** attempt * 5, 60.0)
                print(f"  Rate limited ({e.code}), waiting {wait:.0f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            print(f"ERROR: Anthropic semantic match API returned {e.code}", file=sys.stderr)
            return {}
        except (json.JSONDecodeError, Exception) as e:
            print(f"ERROR: Semantic match failed: {e}", file=sys.stderr)
            return {}


def call_semantic_match(provider, criteria_dict, api_key, model, max_retries=15):
    if provider == "anthropic":
        return call_anthropic_semantic_match(criteria_dict, api_key, model=model, max_retries=max_retries)
    return call_gemini_semantic_match(criteria_dict, api_key, model=model, max_retries=max_retries)


def generate_classification_csv(paths, classified_taxonomy, problem_to_sources, provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL, skip_semantic_match=False, use_batch=False):
    """
    Build the error_classification.csv using LLM-based semantic matching.

    For each submission, pairs of (expert_problem, llm_problem) within the same
    criterion are sent to an LLM to decide if they describe the same root cause.
    This avoids false FP/FN caused by the same problem described with different words.

    The matching cache is persisted to avoid redundant API calls on re-runs.
    """
    import csv

    expert_dir = paths.results_gold_standard
    llm_dir = paths.results_llm
    api_key = get_api_key_for_provider(provider)

    # Load or initialise the semantic match cache
    # Cache key: "{sub_id}|{criterion_id}" → match result dict
    match_cache_file = paths.results_analysis / "semantic_match_cache.json"
    match_cache: dict = {}
    if match_cache_file.exists():
        with match_cache_file.open(encoding="utf-8") as f:
            match_cache = json.load(f)

    # Collect per-submission, per-criterion problems for both evaluators
    sub_crit_data: dict = {}  # {sub_id: {crit_id: {expert: [...], llm: [...]}}}

    for eval_dir, evaluator in [(expert_dir, "expert"), (llm_dir, "llm")]:
        if not eval_dir.exists():
            continue
        for filepath in sorted(eval_dir.glob("*.json")):
            sub_id = filepath.stem
            with filepath.open(encoding="utf-8") as f:
                data = json.load(f)
            if sub_id not in sub_crit_data:
                sub_crit_data[sub_id] = {}
            for crit in data.get("criteria", []):
                cid = crit.get("criterion_id", "")
                if not cid:
                    continue
                if cid not in sub_crit_data[sub_id]:
                    sub_crit_data[sub_id][cid] = {"expert": [], "llm": []}
                for d in crit.get("deductions", []):
                    prob = d.get("problem", "").strip()
                    if prob:
                        sub_crit_data[sub_id][cid][evaluator].append(prob)

    # For each submission, build the criteria dict that needs matching and call LLM
    total_subs = len(sub_crit_data)
    cache_hits = 0
    match_lock = threading.Lock()
    
    # Check if we should use batch mode
    # use_batch is now passed as an argument

    def process_submission(sub_id):
        nonlocal cache_hits
        # Build the criteria that need LLM matching:
        # only those where BOTH evaluators have problems AND not already cached
        to_match = {}
        sub_entry = sub_crit_data[sub_id]
        
        with match_lock:
            for cid, entry in sub_entry.items():
                cache_key = f"{sub_id}|{cid}"
                if entry["expert"] and entry["llm"]:
                    if cache_key not in match_cache:
                        to_match[cid] = {"expert": entry["expert"], "llm": entry["llm"]}
                    else:
                        cache_hits += 1
        return sub_id, to_match

    if use_batch and api_key and provider == "gemini":
        print(f"  Preparing Gemini asynchronous batch for {total_subs} submissions...")
        batch_rows = []
        for sub_id in sorted(sub_crit_data.keys()):
            sid, to_match = process_submission(sub_id)
            if to_match and not skip_semantic_match:
                prompt = SEMANTIC_MATCH_PROMPT.replace("{criteria_json}", json.dumps(to_match, ensure_ascii=False, indent=2))
                batch_rows.append({
                    "custom_id": sub_id,
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "Respond ONLY with a valid JSON object. No markdown."},
                            {"role": "user", "content": prompt}
                        ],
                        "response_format": {"type": "json_object"}
                    }
                })
        
        if batch_rows:
            run_id = f"{paths.experiment_name}-semantic-gemini-{utc_timestamp()}"
            run_dir = classification_run_dir(paths, run_id)
            input_path = run_dir / "semantic.input.jsonl"
            write_jsonl(input_path, batch_rows)
            
            print(f"  Submitting {len(batch_rows)} semantic match requests to Gemini Batch API (SDK)...")
            gemini_requests = []
            submission_ids = []
            for sub_id in sorted(sub_crit_data.keys()):
                sid, to_match = process_submission(sub_id)
                if to_match and not skip_semantic_match:
                    prompt = SEMANTIC_MATCH_PROMPT.replace("{criteria_json}", json.dumps(to_match, ensure_ascii=False, indent=2))
                    gemini_requests.append({
                        "contents": [{"role": "user", "parts": [{"text": f"System: Respond ONLY with a valid JSON object. No markdown.\n\n{prompt}"}]}],
                    })
                    submission_ids.append(sub_id)

            try:
                batch_job = create_gemini_batch_sdk(api_key, model, gemini_requests)
                
                state = {
                    "run_id": run_id,
                    "status": "submitted",
                    "batch_name": batch_job.name,
                    "submission_ids": submission_ids,
                    "provider": "gemini",
                    "created_at": utc_timestamp()
                }
                save_classification_state(paths, state)
                print(f"  Gemini semantic batch submitted: {batch_job.name}")
                return
            except Exception as e:
                if "RESOURCE_EXHAUSTED" in str(e):
                    print(f"  WARNING: Gemini Batch API quota exhausted ({model}). Falling back to regular processing...")
                    # Fall through to the regular processing logic below
                else:
                    raise e
        else:
            print("  No new semantic matches needed.")

    if use_batch and api_key and provider == "anthropic":
        print(f"  Preparing Anthropic Message Batch for {total_subs} submissions...")
        anthropic_requests = []
        submission_ids = []
        for sub_id in sorted(sub_crit_data.keys()):
            sid, to_match = process_submission(sub_id)
            if to_match and not skip_semantic_match:
                prompt = SEMANTIC_MATCH_PROMPT.replace(
                    "{criteria_json}",
                    json.dumps(to_match, ensure_ascii=False, indent=2),
                )
                params = {
                    "model": model,
                    "max_tokens": 16000,
                    "system": "Respond ONLY with a valid JSON object. No markdown.",
                    "messages": [{"role": "user", "content": prompt}],
                }
                if supports_anthropic_temperature(model):
                    params["temperature"] = 0
                anthropic_requests.append({
                    "custom_id": sid,
                    "params": params,
                })
                submission_ids.append(sid)

        if anthropic_requests:
            run_id = f"{paths.experiment_name}-semantic-anthropic-{utc_timestamp()}"
            run_dir = classification_run_dir(paths, run_id)
            input_path = run_dir / "semantic.input.json"
            write_json(input_path, {"requests": anthropic_requests})

            print(f"  Submitting {len(anthropic_requests)} semantic match requests to Anthropic Batch API...")
            batch = create_anthropic_message_batch(api_key, anthropic_requests, timeout_seconds=120)
            write_json(run_dir / "semantic.batch.json", batch)

            state = {
                "run_id": run_id,
                "status": "submitted",
                "batch_id": batch["id"],
                "submission_ids": submission_ids,
                "provider": "anthropic",
                "model": model,
                "created_at": utc_timestamp(),
            }
            save_classification_state(paths, state)
            print(f"  Anthropic semantic batch submitted: {batch['id']} ({batch.get('processing_status')})")
            return
        print("  No new semantic matches needed.")
    
    # Regular processing (used as fallback or when use_batch=False)
    # Process in parallel (serial if max_workers=1)
    total_subs = len(sub_crit_data)
    is_gemini = provider == "gemini"
    provider_label = provider.capitalize()
    print(f"  Processing {total_subs} submissions with {provider_label} ({model})...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        # Sort to keep processing predictable
        sorted_sub_ids = sorted(sub_crit_data.keys())
        for sub_id in sorted_sub_ids:
            sid, to_match = process_submission(sub_id)
            if to_match and not skip_semantic_match and api_key:
                print(f"  Semantic matching {sid} ({len(to_match)} criteria)...")
                try:
                    result = call_semantic_match(provider, to_match, api_key, model=model)
                    with match_lock:
                        for cid, match_result in result.items():
                            cache_key = f"{sid}|{cid}"
                            match_cache[cache_key] = match_result
                        with match_cache_file.open("w", encoding="utf-8") as f:
                            json.dump(match_cache, f, indent=2, ensure_ascii=False)
                    
                    if is_gemini:
                        time.sleep(4.1) # Stay safely below 15 RPM
                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        print(f"  Rate limit hit, waiting 30s...")
                        time.sleep(30)
                    else:
                        print(f"  Error matching {sid}: {e}")

    if cache_hits:
        print(f"  Cache hits: {cache_hits} criteria skipped (already matched)")

    # Now build the CSV rows using the match results
    # Each row: (submission_id, error_category, found_by_expert, found_by_llm)
    # Unit of measurement: individual problem (not criterion, not category)
    rows = []

    for sub_id in sorted(sub_crit_data.keys()):
        for cid, entry in sub_crit_data[sub_id].items():
            expert_probs = entry["expert"]
            llm_probs = entry["llm"]
            cache_key = f"{sub_id}|{cid}"

            if not expert_probs and not llm_probs:
                continue

            if expert_probs and llm_probs and cache_key in match_cache:
                mr = match_cache[cache_key]
                unmatched_llm = set(mr.get("unmatched_llm", []))

                # Support both old format (unmatched_expert/unmatched_human) and new format (covered_expert/uncovered_expert)
                if "covered_expert" in mr:
                    # New format: explicit covered/uncovered lists
                    covered_expert = set(mr.get("covered_expert", []))
                    uncovered_expert = set(mr.get("uncovered_expert", []))
                    # Expert problem is covered if it's in covered_expert OR not in uncovered_expert
                    def is_covered(prob):
                        if covered_expert:
                            return prob in covered_expert
                        return prob not in uncovered_expert
                else:
                    # Old format: unmatched_expert/unmatched_human means uncovered
                    unmatched_expert = set(mr.get("unmatched_expert", mr.get("unmatched_human", [])))
                    def is_covered(prob):
                        return prob not in unmatched_expert

                # 1. Process all Expert problems (Baseline for Recall)
                for prob in expert_probs:
                    cats = classified_taxonomy.get(prob, ["other"])
                    found_by_llm = 1 if is_covered(prob) else 0
                    for cat in cats:
                        rows.append((sub_id, cat, 1, found_by_llm))

                # 2. Process Unmatched LLM problems (Precision penalty)
                for prob in llm_probs:
                    if prob in unmatched_llm:
                        cats = classified_taxonomy.get(prob, ["other"])
                        for cat in cats:
                            rows.append((sub_id, cat, 0, 1))

            elif expert_probs and not llm_probs:
                # All expert problems are FN
                for prob in expert_probs:
                    cats = classified_taxonomy.get(prob, ["other"])
                    for cat in cats:
                        rows.append((sub_id, cat, 1, 0))

            elif llm_probs and not expert_probs:
                # All llm problems are FP
                for prob in llm_probs:
                    cats = classified_taxonomy.get(prob, ["other"])
                    for cat in cats:
                        rows.append((sub_id, cat, 0, 1))

            elif expert_probs and llm_probs and (skip_semantic_match or cache_key not in match_cache):
                # No API key or cache miss (or skip requested) — fallback to independent problems.
                # Avoids assuming alignment without verification (rigorous approach).
                for prob in llm_probs:
                    cats = classified_taxonomy.get(prob, ["other"])
                    for cat in cats:
                        rows.append((sub_id, cat, 0, 1))
                for prob in expert_probs:
                    cats = classified_taxonomy.get(prob, ["other"])
                    for cat in cats:
                        rows.append((sub_id, cat, 1, 0))

    # Deduplicate rows (same sub+cat can appear multiple times from multi-category problems)
    # Aggregate: if any row for (sub, cat) has expert=1 → expert=1; same for llm
    agg: dict = {}
    for sub_id, cat, e, l in rows:
        key = (sub_id, cat)
        if key not in agg:
            agg[key] = [0, 0]
        agg[key][0] = max(agg[key][0], e)
        agg[key][1] = max(agg[key][1], l)

    csv_file = paths.results_analysis / "error_classification.csv"
    with csv_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["submission_id", "error_category", "found_by_expert", "found_by_llm"])
        for (sub_id, cat) in sorted(agg.keys()):
            h, l = agg[(sub_id, cat)]
            writer.writerow([sub_id, cat, h, l])

    print(f"Classification completed (semantic matching). Saved to {csv_file}")

def start_openai_batch_classification(paths, args, unique_problems, classified_taxonomy):
    api_key = get_openai_api_key() if args.provider == "openai" else get_gemini_api_key()
    if not api_key and not args.dry_run:
        raise SystemExit(f"{args.provider.upper()}_API_KEY not found in .env or environment.")

    if args.overwrite_taxonomy:
        classified_taxonomy = {}

    to_classify = [p for p in unique_problems if p not in classified_taxonomy]
    print(f"Found {len(unique_problems)} unique problems across all evaluations.")
    print(f"{len(to_classify)} problems selected for OpenAI batch classification.")

    run_id = args.run_id or f"{paths.experiment_name}-taxonomy-gpt55-{utc_timestamp()}"
    run_dir = classification_run_dir(paths, run_id)
    batch_size = args.batch_size
    batches = [to_classify[i:i + batch_size] for i in range(0, len(to_classify), batch_size)]

    rows = []
    batch_specs = []
    for i, problems in enumerate(batches, start=1):
        custom_id = f"taxonomy-{i:05d}"
        prompt = TAXONOMY_PROMPT.replace("{problems_json}", json.dumps(problems, ensure_ascii=False, indent=2))
        body = build_openai_responses_payload(
            args.model,
            prompt,
            None,
            reasoning_effort=args.reasoning_effort,
            max_output_tokens=args.max_output_tokens,
        )
        rows.append({
            "custom_id": custom_id,
            "method": "POST",
            "url": OPENAI_BATCH_ENDPOINT,
            "body": body,
        })
        batch_specs.append({"custom_id": custom_id, "problems": problems})

    state = {
        "run_id": run_id,
        "status": "created",
        "created_at": utc_timestamp(),
        "updated_at": utc_timestamp(),
        "experiment": paths.experiment_name,
        "provider": args.provider,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "max_output_tokens": args.max_output_tokens,
        "completion_window": args.completion_window,
        "taxonomy_file": str(paths.results_analysis / "error_taxonomy.json"),
        "overwrite_taxonomy": args.overwrite_taxonomy,
        "already_classified_count": len(classified_taxonomy),
        "problem_count": len(to_classify),
        "batch_size": batch_size,
        "batches": batch_specs,
        "openai_batch": {
             "base_url": GEMINI_OPENAI_BASE_URL if args.provider == "gemini" else OPENAI_BASE_URL
        },
    }

    input_path = run_dir / "taxonomy.input.jsonl"
    write_jsonl(input_path, rows)
    state["openai_batch"]["input_path"] = str(input_path)
    state["openai_batch"]["request_count"] = len(rows)

    if args.dry_run:
        state["status"] = "dry_run"
        save_classification_state(paths, state)
        print(f"Dry run written to {input_path}")
        return state

    if not rows:
        write_json(paths.results_analysis / "error_taxonomy.json", classified_taxonomy)
        state["status"] = "completed"
        save_classification_state(paths, state)
        return state

    base_url = state["openai_batch"]["base_url"]
    uploaded_file = openai_upload_batch_file(api_key, input_path, args.timeout_seconds, base_url=base_url)
    write_json(run_dir / "taxonomy.file.json", uploaded_file)
    batch = create_openai_batch(
        api_key,
        uploaded_file["id"],
        args.completion_window,
        {
            "experiment": paths.experiment_name,
            "run_id": run_id,
            "stage": "semantic_taxonomy",
            "model": args.model,
        },
        args.timeout_seconds,
        base_url=base_url
    )
    write_json(run_dir / "taxonomy.batch.json", batch)

    state["status"] = "submitted"
    state["openai_batch"].update({
        "input_file_id": uploaded_file["id"],
        "batch_id": batch["id"],
        "batch_status": batch["status"],
        "submitted_at": utc_timestamp(),
    })
    save_classification_state(paths, state)
    print(f"{args.provider.capitalize()} taxonomy batch submitted: {batch['id']} ({batch['status']})")
    return state

def refresh_openai_taxonomy_batch(api_key, paths, args, state):
    batch_id = state.get("openai_batch", {}).get("batch_id")
    if not batch_id:
        return state
    base_url = state.get("openai_batch", {}).get("base_url", OPENAI_BASE_URL)
    batch = retrieve_openai_batch(api_key, batch_id, args.timeout_seconds, base_url=base_url)
    write_json(classification_run_dir(paths, state["run_id"]) / "taxonomy.batch.json", batch)
    state["openai_batch"].update({
        "batch_status": batch.get("status"),
        "output_file_id": batch.get("output_file_id"),
        "error_file_id": batch.get("error_file_id"),
        "request_counts": batch.get("request_counts"),
        "last_checked_at": utc_timestamp(),
    })
    save_classification_state(paths, state)
    print(f"taxonomy batch {batch_id} is {batch.get('status')}")
    return state

def finalize_openai_batch_classification(paths, args, state, problem_to_sources):
    api_key = get_openai_api_key() if state.get("provider") == "openai" else get_gemini_api_key()
    if not api_key:
        raise SystemExit("API_KEY not found.")

    run_dir = classification_run_dir(paths, state["run_id"])
    batch_state = state["openai_batch"]
    output_file_id = batch_state.get("output_file_id")
    error_file_id = batch_state.get("error_file_id")
    base_url = batch_state.get("base_url", OPENAI_BASE_URL)

    if error_file_id:
        error_path = run_dir / "taxonomy.errors.jsonl"
        error_path.write_bytes(openai_download_file(api_key, error_file_id, args.timeout_seconds, base_url=base_url))
        batch_state["error_path"] = str(error_path)

    if not output_file_id:
        raise RuntimeError("OpenAI taxonomy batch completed without output_file_id.")

    output_path = run_dir / "taxonomy.output.jsonl"
    output_path.write_bytes(openai_download_file(api_key, output_file_id, args.timeout_seconds, base_url=base_url))
    batch_state["output_path"] = str(output_path)

    taxonomy_file = paths.results_analysis / "error_taxonomy.json"
    if taxonomy_file.exists() and not state.get("overwrite_taxonomy"):
        classified_taxonomy = json.loads(taxonomy_file.read_text(encoding="utf-8"))
    else:
        classified_taxonomy = {}

    rows = {row.get("custom_id"): row for row in read_jsonl(output_path)}
    errors = []
    for spec in state.get("batches", []):
        custom_id = spec["custom_id"]
        row = rows.get(custom_id)
        if not row:
            errors.append({"custom_id": custom_id, "error": "missing batch row"})
            continue
        if row.get("error"):
            errors.append({"custom_id": custom_id, "error": row["error"]})
            continue
        try:
            body = response_body_from_batch_row(row)
            text = extract_openai_text(body)
            parsed, _ = robust_json_loads(text)
            if not isinstance(parsed, dict):
                raise RuntimeError("classification response was not a JSON object")
            for problem in spec["problems"]:
                value = parsed.get(problem, ["other"])
                if not isinstance(value, list) or not value:
                    value = ["other"]
                classified_taxonomy[problem] = [str(item) for item in value]
        except Exception as error:
            errors.append({"custom_id": custom_id, "error": str(error)})
            for problem in spec["problems"]:
                classified_taxonomy[problem] = ["other"]

    write_json(taxonomy_file, classified_taxonomy)
    generate_classification_csv(
        paths,
        classified_taxonomy,
        problem_to_sources,
        provider=state.get("provider", DEFAULT_PROVIDER),
        model=state.get("model", DEFAULT_MODEL),
        use_batch=False,
    )
    write_json(run_dir / "taxonomy.processing_errors.json", errors)

    state["status"] = "completed" if not errors else "completed_with_errors"
    state["processing_error_count"] = len(errors)
    state["classified_problem_count"] = len(classified_taxonomy)
    save_classification_state(paths, state)
    print(f"OpenAI taxonomy classification finalized with {len(errors)} processing errors.")
    return state

def refresh_gemini_batch(api_key, paths, args, state):
    batch_name = state.get("batch_name")
    if not batch_name:
        return state
    batch = retrieve_gemini_batch(api_key, batch_name, args.timeout_seconds)
    write_json(classification_run_dir(paths, state["run_id"]) / "batch.json", batch)
    state.update({
        "status": batch.get("state"),
        "output_file": batch.get("output_file"),
        "error_file": batch.get("error_file"),
        "last_checked_at": utc_timestamp(),
    })
    save_classification_state(paths, state)
    print(f"Gemini batch {batch_name} is {batch.get('state')}")
    return state

def finalize_gemini_batch_sdk_results(paths, args, state, job, problem_to_sources):
    api_key = get_gemini_api_key()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY not found.")

    print(f"  Finalizing results for batch {job.name}...")
    
    # Get results from either inlined_responses or output_file
    responses = []
    
    # Mode 1: Inlined Responses (Modern SDK default for small/medium batches)
    if hasattr(job, "dest") and job.dest and hasattr(job.dest, "inlined_responses") and job.dest.inlined_responses:
        print("  Retrieving results from inline batch responses...")
        for resp_item in job.dest.inlined_responses:
            if hasattr(resp_item, "response") and resp_item.response:
                responses.append(resp_item.response)
    
    # Mode 2: File-based output
    if not responses:
        output_file = getattr(job, "output_file", None)
        if not output_file and hasattr(job, "output_config") and job.output_config:
             output_file = getattr(job.output_config, "gcs_destination", None) or getattr(job.output_config, "file_name", None)

        if output_file:
            print(f"  Downloading results from {output_file}...")
            content_bytes = gemini_download_file(api_key, output_file, args.timeout_seconds)
            for line in content_bytes.decode("utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    responses.append(row.get("response", {}))

    if not responses:
        print(f"  Error: No results found in batch job {job.name}.")
        return state

    # Load match cache
    match_cache_file = paths.results_analysis / "semantic_match_cache.json"
    match_cache = {}
    if match_cache_file.exists():
        match_cache = json.loads(match_cache_file.read_text(encoding="utf-8"))

    all_submissions = state.get("submission_ids", [])
    matches_found = 0

    for i, resp in enumerate(responses):
        if i >= len(all_submissions):
            break
        sub_id = all_submissions[i]
        
        # resp can be a dict or a GenerateContentResponse object
        candidates = getattr(resp, "candidates", []) if not isinstance(resp, dict) else resp.get("candidates", [])
        if not candidates:
            continue
            
        # Extract text from first candidate
        candidate = candidates[0]
        content = getattr(candidate, "content", {}) if not isinstance(candidate, dict) else candidate.get("content", {})
        parts = getattr(content, "parts", []) if not isinstance(content, dict) else content.get("parts", [])
        
        if not parts:
            continue
            
        clean_text = getattr(parts[0], "text", "") if not isinstance(parts[0], dict) else parts[0].get("text", "")
        
        match = re.search(r'\{.*\}', clean_text, re.DOTALL)
        if match:
            clean_text = match.group(0)
            
        try:
            match_result = json.loads(clean_text)
            if not isinstance(match_result, dict):
                continue
            for cid, res in match_result.items():
                cache_key = f"{sub_id}|{cid}"
                match_cache[cache_key] = res
                matches_found += 1
        except Exception as e:
            print(f"  Error parsing result for {sub_id}: {e}")

    # Save cache
    write_json(match_cache_file, match_cache)
    
    state["status"] = "finalized"
    state["matches_found"] = matches_found
    save_classification_state(paths, state)
    
    print(f"  Successfully finalized {matches_found} matches for {len(all_submissions)} submissions.")
    return state

def finalize_anthropic_batch_results(paths, args, state, batch, problem_to_sources):
    api_key = get_anthropic_api_key()
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY not found.")

    results_url = batch.get("results_url")
    if not results_url:
        raise RuntimeError(f"Anthropic batch {batch.get('id')} ended without results_url.")

    print(f"  Downloading Anthropic batch results from {results_url}...")
    run_dir = classification_run_dir(paths, state["run_id"])
    results_bytes = download_anthropic_results(api_key, results_url, args.timeout_seconds)
    results_path = run_dir / "semantic.output.jsonl"
    results_path.write_bytes(results_bytes)

    match_cache_file = paths.results_analysis / "semantic_match_cache.json"
    match_cache = {}
    if match_cache_file.exists():
        match_cache = json.loads(match_cache_file.read_text(encoding="utf-8"))

    matches_found = 0
    errors = []

    for line in results_bytes.decode("utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        sub_id = row.get("custom_id")
        result = row.get("result", {})
        if result.get("type") != "succeeded":
            errors.append({"custom_id": sub_id, "error": result.get("error")})
            continue
        try:
            clean_text = extract_anthropic_text(result.get("message", {}))
            match = re.search(r'\{.*\}', clean_text, re.DOTALL)
            if match:
                clean_text = match.group(0)
            match_result = json.loads(clean_text)
            if not isinstance(match_result, dict):
                continue
            for cid, res in match_result.items():
                cache_key = f"{sub_id}|{cid}"
                match_cache[cache_key] = res
                matches_found += 1
        except Exception as error:
            errors.append({"custom_id": sub_id, "error": str(error)})

    write_json(match_cache_file, match_cache)
    if errors:
        write_json(run_dir / "semantic.errors.json", errors)

    taxonomy_file = paths.results_analysis / "error_taxonomy.json"
    if taxonomy_file.exists():
        classified_taxonomy = json.loads(taxonomy_file.read_text(encoding="utf-8"))
        generate_classification_csv(
            paths,
            classified_taxonomy,
            problem_to_sources,
            provider=state.get("provider", DEFAULT_PROVIDER),
            model=state.get("model", DEFAULT_MODEL),
            skip_semantic_match=True,
            use_batch=False,
        )

    state["status"] = "completed"
    state["matches_found"] = matches_found
    state["error_count"] = len(errors)
    save_classification_state(paths, state)
    print(f"  Successfully finalized {matches_found} matches ({len(errors)} errors).")
    return state

def run_anthropic_batch_mode(paths, args, unique_problems, problem_to_sources, classified_taxonomy):
    api_key = get_anthropic_api_key()

    if args.action == "start":
        return generate_classification_csv(
            paths,
            classified_taxonomy,
            problem_to_sources,
            provider="anthropic",
            model=args.model,
            use_batch=True,
        )

    run_id = args.run_id or resolve_latest_classification_run_id(paths)
    if not run_id:
        if args.action == "status":
            raise SystemExit("No latest Anthropic batch run found.")
        return generate_classification_csv(
            paths,
            classified_taxonomy,
            problem_to_sources,
            provider="anthropic",
            model=args.model,
            use_batch=True,
        )

    state = load_classification_state(paths, run_id)
    if state.get("provider") != "anthropic" or not state.get("batch_id"):
        raise SystemExit(f"Run {run_id} is not an Anthropic batch run.")

    if args.action == "status":
        batch_id = state.get("batch_id")
        if api_key and batch_id and state.get("status") != "completed":
            batch = retrieve_anthropic_message_batch(api_key, batch_id, args.timeout_seconds)
            state["status"] = batch.get("processing_status")
            save_classification_state(paths, state)
        print(f"Run: {state['run_id']}")
        print(f"Status: {state.get('status')}")
        print(f"Batch: {state.get('batch_id')}")
        return state

    started = time.monotonic()
    while True:
        if not api_key:
            raise SystemExit("ANTHROPIC_API_KEY not found.")

        batch_id = state.get("batch_id")
        batch = retrieve_anthropic_message_batch(api_key, batch_id, args.timeout_seconds)
        write_json(classification_run_dir(paths, state["run_id"]) / "semantic.batch.json", batch)
        processing_status = batch.get("processing_status")
        state["status"] = processing_status
        save_classification_state(paths, state)

        if processing_status in ANTHROPIC_TERMINAL_BATCH_STATUSES:
            if processing_status != "ended":
                print(f"Anthropic batch job ended with status: {processing_status}")
                return state
            return finalize_anthropic_batch_results(paths, args, state, batch, problem_to_sources)

        if not args.wait:
            return state
        if args.max_wait_seconds > 0 and time.monotonic() - started >= args.max_wait_seconds:
            print("Max wait reached; run can be resumed later with --action advance.")
            return state
        time.sleep(args.poll_seconds)

def run_gemini_batch_mode(paths, args, unique_problems, problem_to_sources, classified_taxonomy):
    api_key = get_gemini_api_key()
    
    # In this script, we use Gemini Batch specifically for semantic matching (Stage 2),
    # as Stage 1 (Taxonomy) is already very efficient with regular Gemini calls.
    
    if args.action == "start":
        return generate_classification_csv(
            paths,
            classified_taxonomy,
            problem_to_sources,
            provider="gemini",
            model=args.model,
            use_batch=True,
        )

    run_id = args.run_id or resolve_latest_classification_run_id(paths)
    if not run_id:
        if args.action == "status":
            raise SystemExit("No latest Gemini batch run found.")
        return generate_classification_csv(
            paths,
            classified_taxonomy,
            problem_to_sources,
            provider="gemini",
            model=args.model,
            use_batch=True,
        )
    
    state = load_classification_state(paths, run_id)
    if state.get("batch_name") is None:
        # This was likely an OpenAI run or something else
        raise SystemExit(f"Run {run_id} is not a Gemini batch run.")

    if args.action == "status":
        batch_name = state.get("batch_name")
        if api_key and batch_name and state.get("status") != "SUCCEEDED":
            job = retrieve_gemini_batch_sdk(api_key, batch_name)
            state["status"] = job.state
            save_classification_state(paths, state)
        
        print(f"Run: {state['run_id']}")
        print(f"Status: {state.get('status')}")
        print(f"Batch: {state.get('batch_name')}")
        return state

    started = time.monotonic()
    while True:
        if not api_key:
            raise SystemExit("GEMINI_API_KEY not found.")

        batch_name = state.get("batch_name")
        job = retrieve_gemini_batch_sdk(api_key, batch_name)
        state["status"] = job.state.name
        
        if job.state.name in {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED"}:
            if job.state.name != "JOB_STATE_SUCCEEDED":
                state["status"] = job.state.name
                save_classification_state(paths, state)
                print(f"Gemini batch job failed: {job.state.name}")
                return state
            
            save_classification_state(paths, state)
            return finalize_gemini_batch_sdk_results(paths, args, state, job, problem_to_sources)

        if not args.wait:
            return state
        if args.max_wait_seconds > 0 and time.monotonic() - started >= args.max_wait_seconds:
            print("Max wait reached; run can be resumed later with --action status.")
            return state
        time.sleep(args.poll_seconds)

        if not args.wait:
            return state
        if args.max_wait_seconds > 0 and time.monotonic() - started >= args.max_wait_seconds:
            print("Max wait reached; run can be resumed later with --action advance.")
            return state
        time.sleep(args.poll_seconds)

def run_openai_batch_mode(paths, args, unique_problems, problem_to_sources, classified_taxonomy):
    api_key = get_openai_api_key()
    if args.action == "start":
        return start_openai_batch_classification(paths, args, unique_problems, classified_taxonomy)

    run_id = args.run_id or resolve_latest_classification_run_id(paths)
    if not run_id:
        if args.action == "status":
            raise SystemExit("No latest OpenAI taxonomy batch run found.")
        state = start_openai_batch_classification(paths, args, unique_problems, classified_taxonomy)
    else:
        state = load_classification_state(paths, run_id)

    if args.action == "status":
        if api_key and state.get("status") not in {"completed", "completed_with_errors", "failed", "dry_run"}:
            state = refresh_openai_taxonomy_batch(api_key, paths, args, state)
        print(f"Run: {state['run_id']}")
        print(f"Status: {state.get('status')}")
        print(f"Batch: {state.get('openai_batch', {}).get('batch_id')} ({state.get('openai_batch', {}).get('batch_status')})")
        print(f"Request counts: {state.get('openai_batch', {}).get('request_counts')}")
        return state

    started = time.monotonic()
    while True:
        if not api_key:
            raise SystemExit("OPENAI_API_KEY not found in .env or environment.")

        state = refresh_openai_taxonomy_batch(api_key, paths, args, state)
        batch_status = state.get("openai_batch", {}).get("batch_status")
        if batch_status in TERMINAL_BATCH_STATUSES:
            if batch_status != "completed":
                state["status"] = "failed"
                save_classification_state(paths, state)
                return state
            return finalize_openai_batch_classification(paths, args, state, problem_to_sources)

        if not args.wait:
            return state
        if args.max_wait_seconds > 0 and time.monotonic() - started >= args.max_wait_seconds:
            print("Max wait reached; run can be resumed later with --action advance.")
            return state
        time.sleep(args.poll_seconds)

def call_gemini_batch_classification(problems_list, api_key, model="gemini-1.5-flash", max_retries=3):
    """Call Google Gemini API for classification."""
    query = urlencode({"key": api_key})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?{query}"
    
    prompt = TAXONOMY_PROMPT.replace("{problems_json}", json.dumps(problems_list, ensure_ascii=False, indent=2))
    
    payload = json.dumps({
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": "Respond ONLY with a valid JSON object mapping strings to arrays of strings. Do not use markdown."}]
        },
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")

    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    for attempt in range(max_retries + 1):
        try:
            with urlopen(request, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
            
            parts = []
            for candidate in result.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if text := part.get("text"):
                        parts.append(text)
            
            clean_text = "".join(parts).strip()
            
            # Find the JSON object using regex
            match = re.search(r'\{.*\}', clean_text, re.DOTALL)
            if match:
                clean_text = match.group(0)
                
            classifications = json.loads(clean_text)
            if not isinstance(classifications, dict):
                classifications = {p: ["other"] for p in problems_list}
            return classifications

        except HTTPError as e:
            if e.code in {429, 503} and attempt < max_retries:
                wait = 30
                print(f"  Rate limited ({e.code}), waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            
            print(f"ERROR: Gemini API returned {e.code}", file=sys.stderr)
            return {p: ["other"] for p in problems_list}
        except json.JSONDecodeError:
            print(f"ERROR: Failed to parse LLM response. Returned default.", file=sys.stderr)
            return {p: ["other"] for p in problems_list}


def call_anthropic_batch_classification(problems_list, api_key, model="claude-sonnet-5", max_retries=3):
    """Call Anthropic Claude API for taxonomy classification."""
    prompt = TAXONOMY_PROMPT.replace("{problems_json}", json.dumps(problems_list, ensure_ascii=False, indent=2))

    for attempt in range(max_retries + 1):
        try:
            clean_text, _ = call_anthropic(
                api_key,
                model,
                prompt,
                temperature=0.0,
                timeout_seconds=120,
                system_prompt=(
                    "Respond ONLY with a valid JSON object mapping strings to arrays of strings. "
                    "Do not use markdown."
                ),
            )
            match = re.search(r'\{.*\}', clean_text, re.DOTALL)
            if match:
                clean_text = match.group(0)
            classifications = json.loads(clean_text)
            if not isinstance(classifications, dict):
                classifications = {p: ["other"] for p in problems_list}
            return classifications
        except HTTPError as e:
            if e.code in {429, 503, 529} and attempt < max_retries:
                wait = min(2 ** attempt * 5, 60.0)
                print(f"  Rate limited ({e.code}), waiting {wait:.0f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            print(f"ERROR: Anthropic API returned {e.code}", file=sys.stderr)
            return {p: ["other"] for p in problems_list}
        except json.JSONDecodeError:
            print("ERROR: Failed to parse Claude response. Returned default.", file=sys.stderr)
            return {p: ["other"] for p in problems_list}


def call_taxonomy_classification(provider, problems_list, api_key, model):
    if provider == "anthropic":
        return call_anthropic_batch_classification(problems_list, api_key, model=model)
    return call_gemini_batch_classification(problems_list, api_key, model=model)


def run_provider_classification(paths, args, unique_problems, problem_to_sources, classified_taxonomy):
    provider = args.provider
    api_key = get_api_key_for_provider(provider)
    taxonomy_file = paths.results_analysis / "error_taxonomy.json"
    semantic_model = resolve_provider_model(provider, args.model, role="semantic")
    taxonomy_model = resolve_provider_model(provider, args.model, role="taxonomy")

    if not api_key and not taxonomy_file.exists():
        print(f"ERROR: {provider.upper()}_API_KEY environment variable not set and no cached taxonomy found.")
        sys.exit(1)
    elif not api_key:
        print(f"WARNING: {provider.upper()}_API_KEY not set. Using cached taxonomy to regenerate CSV only.")

    print(f"Found {len(unique_problems)} unique problems across all evaluations.")
    to_classify = [p for p in unique_problems if p not in classified_taxonomy]
    print(f"{len(unique_problems)} unique problems found.")

    if to_classify and not args.skip_classification and api_key:
        print(f"{len(to_classify)} new problems to classify with {provider} ({taxonomy_model}).")
        batch_size = 50
        batches = [to_classify[i:i + batch_size] for i in range(0, len(to_classify), batch_size)]
        taxonomy_lock = threading.Lock()

        def process_taxonomy_batch(i, batch):
            print(f"Classifying batch {i+1}/{len(batches)} ({len(batch)} problems)...")
            try:
                batch_results = call_taxonomy_classification(provider, batch, api_key, taxonomy_model)
                with taxonomy_lock:
                    for prob in batch:
                        classified_taxonomy[prob] = batch_results.get(prob, ["other"])
                    with taxonomy_file.open("w", encoding="utf-8") as f:
                        json.dump(classified_taxonomy, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"  Error in taxonomy batch {i+1}: {e}")

        max_workers = 5 if provider == "gemini" else 3
        print(f"  Classifying {len(batches)} taxonomy batches in parallel...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_taxonomy_batch, i, batch): i for i, batch in enumerate(batches)}
            concurrent.futures.wait(futures)

        with taxonomy_file.open("w", encoding="utf-8") as f:
            json.dump(classified_taxonomy, f, indent=2, ensure_ascii=False)
    elif to_classify:
        if args.skip_classification:
            print(f"DEBUG: Skipping classification of {len(to_classify)} problems as requested.")
        else:
            print(f"WARNING: {len(to_classify)} new problems have no cached classification. Defaulting to 'other'.")
        for prob in to_classify:
            if prob not in classified_taxonomy:
                classified_taxonomy[prob] = ["other"]

    generate_classification_csv(
        paths,
        classified_taxonomy,
        problem_to_sources,
        provider=provider,
        model=semantic_model,
        skip_semantic_match=args.skip_semantic_match,
    )


def get_unique_problems(paths):
    expert_dir = paths.results_gold_standard
    llm_dir = paths.results_llm
    
    unique_problems = set()
    problem_to_sources = {}
    
    for eval_dir in [expert_dir, llm_dir]:
        if not eval_dir.exists():
            continue

        # Normalize evaluator to 'expert' or 'llm' regardless of directory name
        evaluator = "expert" if eval_dir == expert_dir else "llm"
        for filepath in eval_dir.glob("*.json"):
            sub_id = filepath.stem
            with filepath.open(encoding="utf-8") as f:
                data = json.load(f)

            for crit in data.get("criteria", []):
                for ded in crit.get("deductions", []):
                    prob = ded.get("problem", "").strip()
                    if prob:
                        unique_problems.add(prob)
                        source_key = f"{sub_id}|{evaluator}"  # Use | to avoid split ambiguity
                        if prob not in problem_to_sources:
                            problem_to_sources[prob] = []
                        problem_to_sources[prob].append(source_key)

            for item in data.get("feedback_items", []):
                prob = item.get("problem", "").strip()
                if prob:
                    unique_problems.add(prob)
                    source_key = f"{sub_id}|{evaluator}"  # Use | to avoid split ambiguity
                    if prob not in problem_to_sources:
                        problem_to_sources[prob] = []
                    problem_to_sources[prob].append(source_key)
                    
    return list(unique_problems), problem_to_sources

def main():
    parser = argparse.ArgumentParser(description="Semantically classify errors with LLM.")
    add_experiment_argument(parser)
    parser.add_argument("--provider", choices=["gemini", "openai", "anthropic"], default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Classifier / semantic adjudicator model name.")
    parser.add_argument("--batch", action="store_true", help="Use provider batch API for semantic matching.")
    parser.add_argument("--action", choices=["start", "advance", "status"], default="advance")
    parser.add_argument("--run-id", help="OpenAI classification batch run id.")
    parser.add_argument("--wait", action="store_true", help="Poll OpenAI batch until it completes or max wait is reached.")
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--max-wait-seconds", type=float, default=0.0)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--completion-window", default="24h")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--reasoning-effort", choices=["minimal", "low", "medium", "high", "xhigh"], default="high")
    parser.add_argument("--max-output-tokens", type=int, default=12000)
    parser.add_argument("--overwrite-taxonomy", action="store_true", help="Ignore cached taxonomy and reclassify all problems.")
    parser.add_argument("--skip-classification", action="store_true", help="Skip API classification and use only cached/manual data.")
    parser.add_argument("--skip-semantic-match", action="store_true", help="Skip API semantic matching and use only cached data.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    paths = ExperimentPaths(args.experiment)
    paths.dry_run = args.dry_run # Pass dry_run flag to paths object for convenience
    
    out_dir = paths.results_analysis
    taxonomy_file = out_dir / "error_taxonomy.json"
    
    # Load existing to avoid re-classification
    classified_taxonomy = {}
    if taxonomy_file.exists() and not args.overwrite_taxonomy:
        with taxonomy_file.open(encoding="utf-8") as f:
            classified_taxonomy = json.load(f)
            
    unique_problems, problem_to_sources = get_unique_problems(paths)

    if args.provider == "openai":
        if not args.batch:
            raise SystemExit("OpenAI/gpt-5.5 semantic classification must use --batch.")
        args.model = resolve_provider_model("openai", args.model, role="taxonomy")
        run_openai_batch_mode(paths, args, unique_problems, problem_to_sources, classified_taxonomy)
        return

    if args.provider == "gemini" and args.batch:
        args.model = resolve_provider_model("gemini", args.model, role="semantic")
        run_gemini_batch_mode(paths, args, unique_problems, problem_to_sources, classified_taxonomy)
        return

    if args.provider == "anthropic" and args.batch:
        args.model = resolve_provider_model("anthropic", args.model, role="semantic")
        run_anthropic_batch_mode(paths, args, unique_problems, problem_to_sources, classified_taxonomy)
        return

    run_provider_classification(paths, args, unique_problems, problem_to_sources, classified_taxonomy)

if __name__ == "__main__":
    main()
