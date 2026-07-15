#!/usr/bin/env python3

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, add_experiment_argument


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def render_template(template_text, values):
    rendered = template_text
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def ensure_rubric_ready(rubric):
    if not rubric.get("rubric_ready"):
        raise SystemExit("rubric.json has not been filled out yet (rubric_ready=false).")


def load_manifest_entries(paths):
    official_path = paths.official_sample
    official = load_json(official_path)["entries"] if official_path.exists() else []
    pretest_path = paths.manifests_dir / "pretest_sample.json"
    pretest = load_json(pretest_path)["entries"] if pretest_path.exists() else []
    return official + pretest


def load_optional_text(path, fallback):
    if not path.exists():
        return fallback
    return path.read_text(encoding="utf-8").strip()


def build_experiment_metadata(config, submission_id, role):
    payload = {
        "experiment_id": config.get("experiment_id", config.get("experiment_name", "")),
        "submission_id": submission_id,
        "role": role,
        "provider": config["llm_protocol"].get("provider"),
        "model": config["llm_protocol"].get("model"),
        "temperature": config["llm_protocol"]["temperature"],
        "reasoning_effort": config["llm_protocol"].get("reasoning_effort"),
        "prompt_version": config["llm_protocol"]["prompt_version"],
        "confidence_labels": config["confidence_labels"],
        "architecture": config["llm_protocol"].get("architecture", "two_stage")
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Renders the complete prompt for both stages per submission.")
    from pipeline.paths import add_experiment_argument
    add_experiment_argument(parser)
    return parser.parse_args()


def main():
    args = parse_args()
    paths = ExperimentPaths(args.experiment)

    config = load_json(paths.experiment_config)
    rubric = load_json(paths.rubric)
    ensure_rubric_ready(rubric)

    template_s1 = paths.prompt_template_stage1.read_text(encoding="utf-8")
    template_s2 = paths.prompt_template_stage2.read_text(encoding="utf-8")
    
    schema_s1 = paths.schema_stage1.read_text(encoding="utf-8").strip()
    schema_s2 = paths.schema_stage2.read_text(encoding="utf-8").strip()

    prompt_dir = paths.rendered_prompts_dir
    prompt_dir.mkdir(parents=True, exist_ok=True)
    # Clear only existing stage1 and stage2 files
    for path in prompt_dir.glob("*.md"):
        if ".stage" in path.name:
            path.unlink()

    manifest_entries = load_manifest_entries(paths)
    rubric_json = json.dumps(rubric, ensure_ascii=False, indent=2)

    # Modular texts
    lab_spec_text = load_optional_text(paths.lab_specification, "Specification not found.")
    core_evaluation_text = load_optional_text(paths.evaluation_principles, "Core principles not found.")
    abstract_calibration_text = load_optional_text(paths.abstract_calibration, "Abstract calibration not found.")
    grading_sheet_text = load_optional_text(paths.grading_reference, "Grading sheet not found.")
    comment_style_text = load_optional_text(paths.feedback_style_guide, "Feedback guide not found.")
    starter_scaffold_text = load_optional_text(paths.starter_scaffold, "Starter scaffold not found.")

    for entry in manifest_entries:
        submission_id = entry["submission_id"]
        role = entry.get("role", "student")
        submission_package_path = paths.submissions_dir / f"{submission_id}.md"
        if not submission_package_path.exists():
            print(f"  WARNING: package not found for {submission_id}, skipping.")
            continue
        submission_package = submission_package_path.read_text(encoding="utf-8")

        metadata_var = build_experiment_metadata(config, submission_id, role)

        # Stage 1 Values
        values_stage1 = {
            "EXPERIMENT_METADATA": metadata_var,
            "CORE_EVALUATION_TEXT": core_evaluation_text,
            "ABSTRACT_CALIBRATION_TEXT": abstract_calibration_text,
            "RUBRIC_JSON": rubric_json,
            "SUBMISSION_PACKAGE": submission_package,
            "OUTPUT_SCHEMA_JSON": schema_s1,
            "LAB_SPEC_TEXT": lab_spec_text,
            "GRADING_SHEET_TEXT": grading_sheet_text,
            "STARTER_SCAFFOLD_TEXT": starter_scaffold_text,
        }
        
        # Stage 2 Values
        values_stage2 = {
            "EXPERIMENT_METADATA": metadata_var,
            "COMMENT_STYLE_TEXT": comment_style_text,
            "RUBRIC_JSON": rubric_json,
            "SUBMISSION_PACKAGE": submission_package,
            "OUTPUT_SCHEMA_JSON": schema_s2,
            "STAGE1_JSON": "{{STAGE1_JSON}}" # Will be dynamically injected via llm_execution
        }

        rendered_s1 = render_template(template_s1, values_stage1)
        rendered_s2 = render_template(template_s2, values_stage2)
        
        (prompt_dir / f"{submission_id}.stage1.md").write_text(rendered_s1, encoding="utf-8")
        (prompt_dir / f"{submission_id}.stage2.md").write_text(rendered_s2, encoding="utf-8")

    print(f"Stage 1 and 2 prompts generated in: {prompt_dir}")


if __name__ == "__main__":
    main()
