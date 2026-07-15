#!/usr/bin/env python3
"""
Calculate error overlap metrics (Precision, Recall, F1)
based on the semantically classified errors.
"""

import json
import csv
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.paths import ExperimentPaths, add_experiment_argument
import argparse

def main():
    parser = argparse.ArgumentParser(description="Calculate error overlap metrics.")
    add_experiment_argument(parser)
    args = parser.parse_args()
    paths = ExperimentPaths(args.experiment)
    
    csv_file = paths.results_analysis / "error_classification.csv"
    if not csv_file.exists():
        print(f"Error: {csv_file} not found. Run 12_classify_feedback_errors.py first.")
        sys.exit(1)
        
    out_dir = paths.results_analysis
    
    submission_metrics = {}
    category_metrics = defaultdict(lambda: {'TP': 0, 'FP': 0, 'FN': 0, 'TN': 0})
    
    total_expert = 0
    total_llm = 0
    total_tp = 0
    
    with csv_file.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sub = row['submission_id']
            cat = row['error_category']
            e = int(row['found_by_expert'])
            l = int(row['found_by_llm'])
            
            if sub not in submission_metrics:
                submission_metrics[sub] = {'expected': 0, 'llm_found': 0, 'intersection': 0, 'additional': 0, 'missed': 0}
                
            if e == 1:
                submission_metrics[sub]['expected'] += 1
                total_expert += 1
            if l == 1:
                submission_metrics[sub]['llm_found'] += 1
                total_llm += 1
                
            if e == 1 and l == 1:
                submission_metrics[sub]['intersection'] += 1
                category_metrics[cat]['TP'] += 1
                total_tp += 1
            elif e == 0 and l == 1:
                submission_metrics[sub]['additional'] += 1
                category_metrics[cat]['FP'] += 1
            elif e == 1 and l == 0:
                submission_metrics[sub]['missed'] += 1
                category_metrics[cat]['FN'] += 1
            else:
                category_metrics[cat]['TN'] += 1
                
    # Calculate global metrics
    global_precision = total_tp / total_llm if total_llm > 0 else 0
    global_recall = total_tp / total_expert if total_expert > 0 else 0
    global_f1 = 2 * (global_precision * global_recall) / (global_precision + global_recall) if (global_precision + global_recall) > 0 else 0
    
    # Calculate category metrics
    cats_out = {}
    for cat, cm in category_metrics.items():
        p = cm['TP'] / (cm['TP'] + cm['FP']) if (cm['TP'] + cm['FP']) > 0 else 0
        r = cm['TP'] / (cm['TP'] + cm['FN']) if (cm['TP'] + cm['FN']) > 0 else 0
        f1 = 2 * (p * r) / (p + r) if (p + r) > 0 else 0
        cats_out[cat] = {
            'TP': cm['TP'],
            'FP': cm['FP'],
            'FN': cm['FN'],
            'Precision': p,
            'Recall': r,
            'F1': f1
        }
        
    overlap_data = {
        'global_metrics': {
            'total_expected': total_expert,
            'total_llm_found': total_llm,
            'intersection': total_tp,
            'precision': global_precision,
            'recall': global_recall,
            'f1': global_f1
        },
        'category_metrics': cats_out,
        'submission_metrics': submission_metrics
    }
    
    json_out = out_dir / "error_overlap.json"
    with json_out.open("w", encoding="utf-8") as f:
        json.dump(overlap_data, f, indent=2)
        
    print(f"Overlap analysis complete. Saved to {json_out}")
    print(f"Global Precision: {global_precision:.2f}")
    print(f"Global Recall: {global_recall:.2f}")

if __name__ == "__main__":
    main()
