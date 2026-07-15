import hashlib
import json
from pathlib import Path


def prompt_hash(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_submission_metadata(submission_id, paths):
    path = paths.submissions_dir / f"{submission_id}.metadata.json"
    if not path.exists():
        return {}
    return load_json(path)


def normalize_confidence(value, allowed):
    if value in allowed:
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        mapping = {
            "baixa": "low",
            "media": "medium",
            "média": "medium",
            "alta": "high"
        }
        normalized = mapping.get(normalized, normalized)
        if normalized in allowed:
            return normalized
    return allowed[1] if len(allowed) > 1 else "medium"


def normalize_severity(value):
    allowed = {"minor", "moderate", "major", "blocking"}
    if isinstance(value, str):
        normalized = value.strip().lower()
        mapping = {
            "leve": "minor",
            "minor": "minor",
            "moderada": "moderate",
            "moderado": "moderate",
            "moderate": "moderate",
            "grave": "major",
            "major": "major",
            "bloqueante": "blocking",
            "blocking": "blocking",
        }
        normalized = mapping.get(normalized, normalized)
        if normalized in allowed:
            return normalized
    return "moderate"


def normalize_string_list(value):
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_evidence_refs(value, criterion_id):
    if value is None or not isinstance(value, list):
        value = []
    normalized = [str(item).strip() for item in value if str(item).strip()]
    if normalized:
        return normalized
    return [f"model_output:no_explicit_evidence_ref_reported:{criterion_id}"]


def merge_evidence_refs(*groups):
    merged = []
    seen = set()
    for group in groups:
        if not isinstance(group, list):
            continue
        for item in group:
            ref = str(item).strip()
            if not ref or ref in seen:
                continue
            merged.append(ref)
            seen.add(ref)
    concrete = [ref for ref in merged if not ref.startswith("model_output:")]
    return concrete or merged


def should_force_zero(submission_id, paths):
    metadata = load_submission_metadata(submission_id, paths)
    starter = metadata.get("starter_comparison") or {}
    # Similarity label is now in English for research metadata
    return starter.get("similarity_label") in ["identical_to_starter", "identica_ao_starter"]


def is_bonus_criterion(criterion_id):
    return str(criterion_id).startswith("bonus_")


def primary_ref(criterion):
    for ref in criterion.get("evidence_refs", []):
        if not str(ref).startswith("model_output:"):
            return str(ref)
    refs = criterion.get("evidence_refs", [])
    return str(refs[0]) if refs else "no_explicit_location"


def short_text(text, limit=190):
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def normalize_deductions(raw_value, criterion_id, score, max_score, criterion_refs, justification, force_zero):
    expected_loss = max(round(float(max_score) - float(score), 4), 0.0)
    if force_zero:
        return [
            {
                "problem": "A submissao esta identica ao starter code da disciplina neste criterio.",
                "consequence": "Nao ha implementacao adicional relevante para justificar pontuacao neste criterio.",
                "how_to_fix": "Implemente no codigo da submissao a funcionalidade ou o design pedidos pela rubrica.",
                "points_lost": round(float(max_score), 4),
                "severity": "blocking",
                "confidence": "high",
                "rubric_anchor": criterion_id,
                "evidence_refs": criterion_refs,
            }
        ]

    if expected_loss <= 1e-6:
        return []

    raw_items = raw_value if isinstance(raw_value, list) else []
    normalized = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        problem = str(item.get("problem", "") or "").strip()
        consequence = str(item.get("consequence", "") or "").strip()
        how_to_fix = str(item.get("how_to_fix", item.get("fix", "")) or "").strip()
        evidence_refs = merge_evidence_refs(
            normalize_evidence_refs(item.get("evidence_refs", []), criterion_id),
            criterion_refs,
        )
        points_lost = item.get("points_lost")
        if not isinstance(points_lost, (int, float)):
            points_lost = 0.0
        points_lost = max(float(points_lost), 0.0)
        if problem or consequence or how_to_fix:
            confidence = normalize_confidence(item.get("confidence"), ["low", "medium", "high"])
            normalized.append(
                {
                    "problem": problem,
                    "consequence": consequence,
                    "how_to_fix": how_to_fix,
                    "points_lost": points_lost,
                    "severity": normalize_severity(item.get("severity")),
                    "confidence": confidence,
                    "rubric_anchor": str(item.get("rubric_anchor", criterion_id) or criterion_id).strip(),
                    "evidence_refs": evidence_refs,
                }
            )

    if not normalized:
        return [
            {
                "problem": short_text(justification)
                or f"Penalizacao registrada no criterio {criterion_id} sem detalhamento estruturado.",
                "consequence": "A justificativa do criterio nao separou claramente o impacto do problema na nota.",
                "how_to_fix": "Explique exatamente o que esta errado no codigo, por que isso reduz a nota e onde corrigir.",
                "points_lost": expected_loss,
                "severity": "moderate",
                "confidence": "medium",
                "rubric_anchor": criterion_id,
                "evidence_refs": criterion_refs,
            }
        ]

    total_reported = sum(item["points_lost"] for item in normalized)
    if total_reported <= 1e-6:
        normalized[-1]["points_lost"] = expected_loss
        total_reported = expected_loss

    scale = expected_loss / total_reported if total_reported > 0 else 1.0
    accumulated = 0.0
    for index, item in enumerate(normalized):
        if index < len(normalized) - 1:
            item["points_lost"] = round(item["points_lost"] * scale, 4)
            accumulated += item["points_lost"]
        else:
            item["points_lost"] = round(max(expected_loss - accumulated, 0.0), 4)

    diff = round(expected_loss - sum(item["points_lost"] for item in normalized), 4)
    if normalized and abs(diff) > 1e-6:
        normalized[-1]["points_lost"] = round(normalized[-1]["points_lost"] + diff, 4)

    return normalized


def normalize_feedback_items(raw_value, criteria, force_zero):
    if force_zero:
        criterion = criteria[0] if criteria else {"criterion_id": "geral", "criterion_name": "Geral", "evidence_refs": []}
        return [
            {
                "criterion_id": criterion["criterion_id"],
                "criterion_name": criterion["criterion_name"],
                "problem": "A submissao esta identica ao starter code da disciplina.",
                "consequence": "Sem implementacao adicional relevante, a submissao nao ganha pontos nos criterios obrigatorios.",
                "how_to_fix": "Implemente as funcionalidades e o design pedidos no laboratorio e mostre isso no codigo entregue.",
                "severity": "blocking",
                "confidence": "high",
                "evidence_refs": criterion.get("evidence_refs", []),
            }
        ]

    criteria_by_id = {criterion["criterion_id"]: criterion for criterion in criteria}
    normalized = []
    if isinstance(raw_value, list):
        for item in raw_value:
            if not isinstance(item, dict):
                continue
            criterion_id = str(item.get("criterion_id", "") or "").strip()
            criterion = criteria_by_id.get(criterion_id)
            fallback_refs = criterion.get("evidence_refs", []) if criterion else []
            problem = str(item.get("problem", "") or "").strip()
            consequence = str(item.get("consequence", "") or "").strip()
            how_to_fix = str(item.get("how_to_fix", item.get("fix", "")) or "").strip()
            severity = normalize_severity(item.get("severity"))
            confidence = normalize_confidence(item.get("confidence"), ["low", "medium", "high"])
            evidence_refs = merge_evidence_refs(
                normalize_evidence_refs(item.get("evidence_refs", []), criterion_id or "feedback_item"),
                fallback_refs,
            )
            if problem and consequence and how_to_fix:
                normalized.append(
                    {
                        "criterion_id": criterion_id or (criterion["criterion_id"] if criterion else ""),
                        "criterion_name": item.get("criterion_name")
                        or (criterion["criterion_name"] if criterion else ""),
                        "problem": problem,
                        "consequence": consequence,
                        "how_to_fix": how_to_fix,
                        "severity": severity,
                        "confidence": confidence,
                        "evidence_refs": evidence_refs,
                    }
                )

    if normalized:
        return normalized[:6]

    derived = []
    for criterion in criteria:
        for deduction in criterion.get("deductions", []):
            derived.append(
                {
                    "criterion_id": criterion["criterion_id"],
                    "criterion_name": criterion["criterion_name"],
                    "problem": deduction.get("problem", ""),
                    "consequence": deduction.get("consequence", ""),
                    "how_to_fix": deduction.get("how_to_fix", ""),
                    "evidence_refs": deduction.get("evidence_refs", []),
                    "severity": deduction.get("severity", "moderate"),
                    "confidence": deduction.get("confidence", "medium"),
                    "points_lost": deduction.get("points_lost", 0.0),
                }
            )

    if not derived:
        criterion = criteria[0] if criteria else {"criterion_id": "geral", "criterion_name": "Geral", "evidence_refs": []}
        return [
            {
                "criterion_id": criterion["criterion_id"],
                "criterion_name": criterion["criterion_name"],
                "problem": "Nao ha problema relevante nos criterios obrigatorios avaliados.",
                "consequence": "A submissao atende ao que a rubrica atual pede sem descontos expressivos.",
                "how_to_fix": "Mantenha esse padrao e, se quiser evoluir, reforce testes e refinamentos opcionais.",
                "severity": "minor",
                "confidence": "high",
                "evidence_refs": criterion.get("evidence_refs", []),
            }
        ]

    eligible = [item for item in derived if item.get("confidence") != "low"] or derived
    eligible.sort(
        key=lambda item: (
            1 if is_bonus_criterion(item.get("criterion_id")) else 0,
            -float(item.get("points_lost", 0.0)),
            item.get("criterion_id", ""),
        )
    )
    return [
        {
            "criterion_id": item["criterion_id"],
            "criterion_name": item["criterion_name"],
            "problem": item["problem"],
            "consequence": item["consequence"],
            "how_to_fix": item["how_to_fix"],
            "severity": normalize_severity(item.get("severity")),
            "confidence": normalize_confidence(item.get("confidence"), ["low", "medium", "high"]),
            "evidence_refs": item["evidence_refs"],
        }
        for item in eligible[:6]
    ]


def build_student_feedback(feedback_items):
    lines = []
    for item in feedback_items[:6]:
        evidence_refs = item.get("evidence_refs", [])
        ref = next((ref for ref in evidence_refs if not str(ref).startswith("model_output:")), "")
        if not ref:
            ref = evidence_refs[0] if evidence_refs else "sem_localizacao_explicita"
        problem = short_text(item.get("problem", ""), limit=160)
        consequence = short_text(item.get("consequence", ""), limit=170)
        how_to_fix = short_text(item.get("how_to_fix", ""), limit=170)
        lines.append(
            f"[{ref}] Problema: {problem} Consequencia: {consequence} Como consertar: {how_to_fix}"
        )
    return "\n".join(lines)


def weighted_total_score(criteria, rubric):
    rubric_by_id = {criterion["id"]: criterion for criterion in rubric["criteria"]}
    total = 0.0
    for criterion in criteria:
        rubric_criterion = rubric_by_id.get(criterion["criterion_id"])
        if not rubric_criterion:
            continue
        total += float(criterion["score"]) * float(rubric_criterion.get("weight", 1.0))
    total_max = float(rubric.get("score_model", {}).get("total_max_score", 10.0))
    return min(round(total, 4), total_max)


def normalize_llm_payload_stage1(stage1_parsed, submission_id, rubric, paths):
    force_zero = should_force_zero(submission_id, paths)
    criteria_by_id = {criterion.get("criterion_id"): criterion for criterion in stage1_parsed.get("criteria", [])}
    normalized_criteria = []

    for rubric_criterion in rubric["criteria"]:
        criterion_id = rubric_criterion["id"]
        current = criteria_by_id.get(criterion_id, {})
        score = current.get("score", 0)
        if not isinstance(score, (int, float)):
            score = 0
        if force_zero:
            score = 0

        evidence_refs = normalize_evidence_refs(current.get("evidence_refs", []), criterion_id)
        justification = str(current.get("justification", "") or "").strip()
        if force_zero:
            justification = (
                "Submissao identica ao starter code segundo o metadata do experimento; "
                "sem implementacao adicional relevante atribuivel ao estudante neste criterio."
            )
        deductions = normalize_deductions(
            current.get("deductions", []),
            criterion_id,
            score,
            rubric_criterion["max_score"],
            evidence_refs,
            justification,
            force_zero,
        )
        merged_refs = merge_evidence_refs(
            evidence_refs,
            *[item.get("evidence_refs", []) for item in deductions],
        )
        if not justification:
            if deductions:
                justification = (
                    f"O criterio perdeu ponto principalmente por {deductions[0]['problem'].lower()} "
                    f"Veja os descontos detalhados para problema, consequencia e correcao."
                )
            else:
                justification = "Criterio atendido sem descontos relevantes."

        normalized_criteria.append(
            {
                "criterion_id": criterion_id,
                "criterion_name": rubric_criterion["name"],
                "score": score,
                "max_score": rubric_criterion["max_score"],
                "justification": justification,
                "success_evidence": normalize_string_list(current.get("success_evidence", [])),
                "evidence_refs": merged_refs,
                "non_penalized_observations": normalize_string_list(
                    current.get("non_penalized_observations", [])
                ),
                "deductions": deductions,
            }
        )

    return normalized_criteria, force_zero
