# Determinism Benchmark

Study: `gemini_grading_determinism`
Model: `gemini-3.1-pro-preview`

## Run Coverage

| run | experiment | outputs | mean total score | grade MAE vs expert | detection F1 |
| --- | --- | ---: | ---: | ---: | ---: |
| run1 | lab03-filmnow/runs/gemini31pro/run1 | 84 | 8.7321 | 0.5357 | 0.6492 |
| run2 | lab03-filmnow/runs/gemini31pro/run2 | 84 | 8.9074 | 0.3943 | 0.6528 |
| run3 | lab03-filmnow/runs/gemini31pro/run3 | 84 | 8.9083 | 0.3911 | 0.6606 |

## Pairwise Stability

| comparison | n | exact score match % | MAE | mean problem Jaccard |
| --- | ---: | ---: | ---: | ---: |
| run1_vs_run2 | 84 | 7.1% | 0.3884 | 0.0119 |
| run1_vs_run3 | 84 | 8.3% | 0.4065 | 0.0270 |
| run2_vs_run3 | 84 | 9.5% | 0.1854 | 0.0363 |

## Triple-Run Stability

- Compared submissions: 84
- Exact total-score matches across all 3 runs: 2 (2.4%)

