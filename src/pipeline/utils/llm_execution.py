import json
import re
import time
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def extract_text(response_payload):
    parts = []
    for candidate in response_payload.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            text = part.get("text")
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def extract_anthropic_text(response_payload):
    parts = []
    for item in response_payload.get("content", []):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            text = item.get("text")
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def extract_openai_text(response_payload):
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts = []
    for item in response_payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def strip_markdown_fences(text):
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def robust_json_loads(text):
    """Attempt to parse JSON, cleaning common LLM artifacts like trailing braces or text."""
    cleaned = strip_markdown_fences(text).strip()
    try:
        return json.loads(cleaned), {"parse_mode": "direct_json_loads"}
    except json.JSONDecodeError:
        # Fallback: find the first '{' and the matching '}'
        start_idx = cleaned.find('{')
        if start_idx == -1:
            raise
            
        stack = 0
        for i in range(start_idx, len(cleaned)):
            if cleaned[i] == '{':
                stack += 1
            elif cleaned[i] == '}':
                stack -= 1
                if stack == 0:
                    try:
                        return json.loads(cleaned[start_idx : i + 1]), {"parse_mode": "brace_scan_fallback"}
                    except json.JSONDecodeError:
                        break
        raise


def extract_embedded_output_schema(prompt_text):
    marker = "## Required Output Schema"
    if marker not in prompt_text:
        return None
    schema_block = prompt_text.split(marker, 1)[1]
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", schema_block, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def parse_retry_delay_seconds(error_body):
    try:
        payload = json.loads(error_body)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        details = payload.get("error", {}).get("details", [])
        for detail in details:
            retry_delay = detail.get("retryDelay")
            if isinstance(retry_delay, str):
                match = re.match(r"^([0-9]+(?:\.[0-9]+)?)s$", retry_delay.strip())
                if match:
                    return float(match.group(1))

    match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", error_body, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def build_gemini_batch_inline_request(prompt_text, temperature=0, reasoning_effort=None, metadata=None):
    config = {
        "system_instruction": {
            "parts": [{
                "text": (
                    "You are a Computer Science Professor evaluating a programming laboratory. "
                    "Respond ONLY with valid JSON, without additional markdown."
                )
            }]
        },
        "temperature": temperature,
        "response_mime_type": "application/json",
    }
    if reasoning_effort:
        effort_map = {
            "medium": "balanced",
            "xhigh": "high",
        }
        config["thinking_config"] = {
            "thinking_level": effort_map.get(reasoning_effort, reasoning_effort),
        }

    request = {
        "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
        "config": config,
    }
    if metadata:
        request["metadata"] = metadata
    return request


def build_gemini_generate_content_request(prompt_text, temperature=0, reasoning_effort=None):
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "systemInstruction": {
            "parts": [{
                "text": (
                    "You are a Computer Science Professor evaluating a programming laboratory. "
                    "Respond ONLY with valid JSON, without additional markdown."
                )
            }]
        },
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    if reasoning_effort:
        effort_map = {
            "medium": "balanced",
            "xhigh": "high",
        }
        gemini_effort = effort_map.get(reasoning_effort, reasoning_effort)
        payload["generationConfig"]["thinkingConfig"] = {
            "thinking_level": gemini_effort,
        }
    return payload


def call_gemini(api_key, model, prompt_text, temperature, timeout_seconds, reasoning_effort=None):
    payload = build_gemini_generate_content_request(
        prompt_text,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
    )
    query = urlencode({"key": api_key})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?{query}"
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        raw_bytes = response.read()
    response_payload = json.loads(raw_bytes.decode("utf-8"))
    
    return strip_markdown_fences(extract_text(response_payload)), response_payload


def call_github_models(token, model, prompt_text, temperature, timeout_seconds):
    payload = {
        "messages": [
            {"role": "system", "content": "You are a Computer Science Professor evaluating a programming laboratory. Respond ONLY with valid JSON, without additional markdown."},
            {"role": "user", "content": prompt_text}
        ],
        "model": model,
        "temperature": temperature,
        "max_tokens": 4096,
    }
    url = "https://models.github.ai/inference/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=timeout_seconds) as response:
        raw_bytes = response.read()
    response_payload = json.loads(raw_bytes.decode("utf-8"))
    
    content = response_payload["choices"][0]["message"]["content"]
    return strip_markdown_fences(content), response_payload


def build_openai_responses_payload(
    model,
    prompt_text,
    temperature,
    reasoning_effort=None,
    max_output_tokens=20000,
):
    output_schema = extract_embedded_output_schema(prompt_text)
    if output_schema:
        text_format = {
            "type": "json_schema",
            "name": "grading_stage_output",
            "schema": output_schema,
            "strict": False,
        }
    else:
        text_format = {"type": "json_object"}

    model_lower = model.lower()
    supports_temperature = not model_lower.startswith(("gpt-5", "o1", "o3", "o4"))

    payload = {
        "model": model,
        "instructions": (
            "You are a Computer Science Professor evaluating a programming "
            "laboratory. Respond ONLY with valid JSON, without additional markdown."
        ),
        "input": prompt_text,
        "max_output_tokens": max_output_tokens,
        "text": {
            "format": text_format
        },
    }
    if temperature is not None and supports_temperature:
        payload["temperature"] = temperature
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    return payload


def supports_anthropic_temperature(model):
    model_lower = (model or "").lower()
    return not (
        model_lower.startswith("claude-sonnet-5")
        or model_lower.startswith("claude-fable")
    )


def call_anthropic(api_key, model, prompt_text, temperature, timeout_seconds, system_prompt=None):
    system_text = system_prompt or (
        "You are a Computer Science Professor evaluating a programming laboratory. "
        "Respond ONLY with valid JSON, without additional markdown."
    )
    payload = {
        "model": model,
        "max_tokens": 16000,
        "system": system_text,
        "messages": [{"role": "user", "content": prompt_text}],
    }
    if temperature is not None and supports_anthropic_temperature(model):
        payload["temperature"] = temperature

    body = json.dumps(payload).encode("utf-8")
    request = Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        raw_bytes = response.read()
    response_payload = json.loads(raw_bytes.decode("utf-8"))

    return strip_markdown_fences(extract_anthropic_text(response_payload)), response_payload


def call_openai(api_key, model, prompt_text, temperature, timeout_seconds, reasoning_effort=None):
    payload = build_openai_responses_payload(
        model,
        prompt_text,
        temperature,
        reasoning_effort=reasoning_effort,
    )

    body = json.dumps(payload).encode("utf-8")
    request = Request(
        "https://api.openai.com/v1/responses",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        raw_bytes = response.read()
    response_payload = json.loads(raw_bytes.decode("utf-8"))

    return strip_markdown_fences(extract_openai_text(response_payload)), response_payload


def execute_llm_with_retry(
    provider,
    credentials,
    model,
    prompt_text,
    temperature,
    timeout_seconds,
    max_retries,
    retry_default_seconds,
    reasoning_effort=None,
):
    attempt = 0
    while True:
        try:
            if provider == "gemini":
                return call_gemini(credentials, model, prompt_text, temperature, timeout_seconds, reasoning_effort=reasoning_effort)
            elif provider == "openai":
                return call_openai(
                    credentials,
                    model,
                    prompt_text,
                    temperature,
                    timeout_seconds,
                    reasoning_effort=reasoning_effort,
                )
            elif provider == "anthropic":
                return call_anthropic(
                    credentials,
                    model,
                    prompt_text,
                    temperature,
                    timeout_seconds,
                )
            elif provider == "github":
                return call_github_models(credentials, model, prompt_text, temperature, timeout_seconds)
            else:
                raise ValueError(f"Unknown provider: {provider}")
        except HTTPError as error:
            error_body = error.read().decode("utf-8", errors="replace")
            if error.code in {429, 503} and attempt < max_retries:
                retry_seconds = parse_retry_delay_seconds(error_body) or retry_default_seconds
                if provider in {"github", "openai", "anthropic"}:
                    retry_seconds = min(2 ** attempt * 5, 60.0)
                print(f"  temporary API error ({error.code}); waiting {retry_seconds:.1f}s before retry ({attempt + 1}/{max_retries})")
                time.sleep(retry_seconds)
                attempt += 1
                continue
            raise HTTPError(error.url, error.code, error.msg, error.hdrs, None) from RuntimeError(error_body)


def run_two_stage_evaluation(
    provider, credentials, model, 
    prompt_stage1_text, prompt_stage2_template, 
    temperature, timeout_seconds, max_retries, retry_default_seconds,
    reasoning_effort=None,
):
    """
    Orchestrates the two-stage execution. 
    1. Runs stage 1.
    2. Parses stage 1, injects into stage 2 template.
    3. Runs stage 2.
    Returns (stage1_parsed, stage2_parsed, stage1_raw_resp, stage2_raw_resp)
    """
    
    # Stage 1
    t1_text, r1_payload = execute_llm_with_retry(
        provider, credentials, model, prompt_stage1_text, 
        temperature, timeout_seconds, max_retries, retry_default_seconds,
        reasoning_effort=reasoning_effort,
    )
    
    try:
        stage1_parsed, stage1_parse_meta = robust_json_loads(t1_text)
    except Exception as e:
        raise RuntimeError(f"Failed to parse JSON in Stage 1: {e}\nRetrieved text: {t1_text}")
        
    s1_json_str = json.dumps(stage1_parsed, ensure_ascii=False, indent=2)
    prompt_stage2_text = prompt_stage2_template.replace("{{STAGE1_JSON}}", s1_json_str)
    
    # Stage 2
    t2_text, r2_payload = execute_llm_with_retry(
        provider, credentials, model, prompt_stage2_text, 
        temperature, timeout_seconds, max_retries, retry_default_seconds,
        reasoning_effort=reasoning_effort,
    )
    
    try:
        stage2_parsed, stage2_parse_meta = robust_json_loads(t2_text)
    except Exception as e:
        raise RuntimeError(f"Failed to parse JSON in Stage 2: {e}\nRetrieved text: {t2_text}")
        
    parse_audit = {
        "stage1": stage1_parse_meta,
        "stage2": stage2_parse_meta,
        "stage1_raw_text_chars": len(t1_text),
        "stage2_raw_text_chars": len(t2_text),
    }
    return stage1_parsed, stage2_parsed, r1_payload, r2_payload, parse_audit
