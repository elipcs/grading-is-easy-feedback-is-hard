# Determinism Benchmark

Study: `gpt55_grading_determinism`
Model: `gpt-5.5`

## Run Coverage

| run | experiment | outputs | mean total score | grade MAE vs expert | detection F1 |
| --- | --- | ---: | ---: | ---: | ---: |
| run1 | lab03-filmnow/runs/gpt55/run1 | 84 | 7.1123 | 1.6043 | 0.6738 |
| run2 | lab03-filmnow/runs/gpt55/run2 | 84 | 7.3452 | 1.3929 | 0.6639 |
| run3 | lab03-filmnow/runs/gpt55/run3 | 84 | 7.3177 | 1.4311 | 0.6835 |

## Pairwise Stability

| comparison | n | exact score match % | MAE | mean problem Jaccard |
| --- | ---: | ---: | ---: | ---: |
| run1_vs_run2 | 84 | 0.0% | 0.4002 | 0.0000 |
| run1_vs_run3 | 84 | 1.2% | 0.4601 | 0.0000 |
| run2_vs_run3 | 84 | 4.8% | 0.3070 | 0.0000 |

## Triple-Run Stability

- Compared submissions: 84
- Exact total-score matches across all 3 runs: 0 (0.0%)

