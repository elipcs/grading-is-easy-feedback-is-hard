#!/usr/bin/env python3
"""
Triangular Gold Standard Analysis.
Compares Monitor vs Gold Standard and LLM vs Gold Standard.
"""

import json
import csv
import math
import sys
from pathlib import Path
from collections import defaultdict
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, add_experiment_argument

def mae(diffs):
    return sum(abs(d) for d in diffs) / len(diffs) if diffs else 0.0

def load_evaluation(path):
    if not path.exists(): return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)

def count_errors(eval_data):
    if not eval_data: return 0
    count = 0
    for crit in eval_data.get("criteria", []):
        count += len(crit.get("deductions", []))
    return count

def main():
    parser = argparse.ArgumentParser(description="Triangular analysis: Monitor & LLM vs Gold Standard.")
    add_experiment_argument(parser)
    args = parser.parse_args()
    paths = ExperimentPaths(args.experiment)
    
    # Sources
    # GS: outputs/gold_standard (refined data)
    # Monitor: outputs/human (original raw data)
    # LLM: outputs/llm (Gemini results)
    
    expert_dir = paths.results_gold_standard
    mon_dir = paths.results_monitor
    llm_dir = paths.results_llm
    
    all_sids = sorted([p.stem for p in expert_dir.glob("*.json")])
    if not all_sids:
        print(f"No evaluations found in {expert_dir}")
        sys.exit(1)

    results = []
    
    # Aggregate stats
    metrics = {
        "monitor": {"grades": [], "errors": []},
        "llm": {"grades": [], "errors": []},
        "expert": {"grades": [], "errors": []}
    }

    for sid in all_sids:
        expert_eval = load_evaluation(expert_dir / f"{sid}.json")
        mon = load_evaluation(mon_dir / f"{sid}.json")
        llm = load_evaluation(llm_dir / f"{sid}.json")
        
        if not expert_eval or not mon or not llm:
            continue
            
        expert_score = expert_eval.get("total_score", 0.0)
        mon_score = mon.get("total_score", 0.0)
        llm_score = llm.get("total_score", 0.0)
        
        expert_err = count_errors(expert_eval)
        # Note: Monitor (raw) JSON doesn't have structured deductions listed in a loop usually 
        # in the 'criteria' list of the outputs/gold_standard dir, it might just be scores.
        # Let's count structured things if they exist, or fallback to 0.
        mon_err = count_errors(mon) 
        # Actually, if Monitor raw JSON doesn't have deductions, we might need to rely on the Expert error list
        # as the baseline and see what the LLM found.
        llm_err = count_errors(llm)
        
        results.append({
            "submission_id": sid,
            "scores": {"expert": expert_score, "monitor": mon_score, "llm": llm_score},
            "error_counts": {"expert": expert_err, "monitor": mon_err, "llm": llm_err}
        })
        
        metrics["expert"]["grades"].append(expert_score)
        metrics["monitor"]["grades"].append(mon_score)
        metrics["llm"]["grades"].append(llm_score)
        
        metrics["expert"]["errors"].append(expert_err)
        metrics["monitor"]["errors"].append(mon_err)
        metrics["llm"]["errors"].append(llm_err)

    # Compute comparison metrics
    def compare(target_key, baseline_key):
        t_grades = metrics[target_key]["grades"]
        b_grades = metrics[baseline_key]["grades"]
        diffs = [t - b for t, b in zip(t_grades, b_grades)]
        return {
            "mae": mae(diffs),
            "bias": sum(diffs) / len(diffs) if diffs else 0.0
        }

    analysis = {
        "monitor_vs_expert": compare("monitor", "expert"),
        "llm_vs_expert": compare("llm", "expert"),
        "submissions": results
    }
    
    out_path = paths.results_analysis / "triangular_analysis.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2)
        
    print(f"Triangular analysis complete. Saved to {out_path}")
    print(f"Monitor vs Expert: MAE={analysis['monitor_vs_expert']['mae']:.2f}")
    print(f"LLM vs Expert:     MAE={analysis['llm_vs_expert']['mae']:.2f}")

if __name__ == "__main__":
    main()
