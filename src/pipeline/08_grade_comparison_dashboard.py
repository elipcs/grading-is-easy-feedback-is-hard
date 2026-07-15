#!/usr/bin/env python3
"""
Grade Comparison Dashboard data preparation.
Calculates statistical metrics for grading agreement (RQ2).
"""

import json
import csv
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, add_experiment_argument
import argparse

def mae(diffs):
    return sum(abs(d) for d in diffs) / len(diffs) if diffs else None

def rmse(diffs):
    return math.sqrt(sum(d * d for d in diffs) / len(diffs)) if diffs else None

def main():
    parser = argparse.ArgumentParser(description="Calculate grade comparison metrics.")
    add_experiment_argument(parser)
    args = parser.parse_args()
    paths = ExperimentPaths(args.experiment)
    
    expert_dir = paths.results_gold_standard
    llm_dir = paths.results_llm
    
    if not llm_dir.exists():
        print(f"Error: {llm_dir} not found. Run 11_collect_llm_results.py first.")
        sys.exit(1)
        
    out_dir = paths.results_analysis
    
    # Collect scores
    expert_scores = {}
    expert_crit_scores = {}
    for fp in expert_dir.glob("*.json"):
        with fp.open(encoding="utf-8") as f:
            data = json.load(f)
            expert_scores[data["submission_id"]] = data["total_score"]
            expert_crit_scores[data["submission_id"]] = {c["criterion_id"]: c["score"] for c in data.get("criteria", [])}
            
    llm_scores = {}
    llm_crit_scores = {}
    for fp in llm_dir.glob("*.json"):
        with fp.open(encoding="utf-8") as f:
            data = json.load(f)
            llm_scores[data["submission_id"]] = data["total_score"]
            llm_crit_scores[data["submission_id"]] = {c["criterion_id"]: c["score"] for c in data.get("criteria", [])}
            
    # Intersect
    common_subs = sorted(list(set(expert_scores.keys()) & set(llm_scores.keys())))
    
    es = [expert_scores[s] for s in common_subs]
    ls = [llm_scores[s] for s in common_subs]
    diffs = [l - e for e, l in zip(es, ls)]
    
    mean_diff = sum(diffs) / len(diffs) if diffs else 0
    std_diff = math.sqrt(sum((d - mean_diff)**2 for d in diffs) / (len(diffs)-1)) if len(diffs)>1 else 0
    
    bland_altman = {
        "mean_bias": mean_diff,
        "upper_limit": mean_diff + 1.96 * std_diff,
        "lower_limit": mean_diff - 1.96 * std_diff,
        "points": [{"x": (e+l)/2, "y": l-e} for e, l in zip(es, ls)]
    }
    
    # Category level
    categories = list(expert_crit_scores[common_subs[0]].keys()) if common_subs else []
    crit_metrics = {}
    
    for cat in categories:
        c_es = [expert_crit_scores[s].get(cat, 0) for s in common_subs]
        c_ls = [llm_crit_scores[s].get(cat, 0) for s in common_subs]
        c_diffs = [l - e for e, l in zip(c_es, c_ls)]
        
        crit_metrics[cat] = {
            "mae": mae(c_diffs),
            "rmse": rmse(c_diffs),
            "mean_bias": sum(c_diffs)/len(c_diffs) if c_diffs else 0
        }
        
    grade_data = {
        "overall": {
            "n": len(common_subs),
            "mae": mae(diffs),
            "rmse": rmse(diffs),
            "mean_bias": mean_diff,
            "scatter_points": [{"expert": e, "llm": l, "submission": s} for e, l, s in zip(es, ls, common_subs)]
        },
        "bland_altman": bland_altman,
        "by_criterion": crit_metrics
    }
    
    json_out = out_dir / "grade_comparison.json"
    with json_out.open("w", encoding="utf-8") as f:
        json.dump(grade_data, f, indent=2)
        
    print(f"Grade comparison complete. Saved to {json_out}")
    print(f"Overall MAE: {grade_data['overall']['mae']:.3f}")

if __name__ == "__main__":
    main()
