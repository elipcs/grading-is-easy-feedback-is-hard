# Run-to-Run Stability (Paper Table)

Stability under a fixed protocol (`n = 84` submissions per model).

| Model | ICC(2,1) | Run-pair MAE | Exact match | Within ±1.0 |
| --- | ---: | ---: | ---: | ---: |
| Gemini 3.1 Pro | 0.89 | 0.33 | 2.4% | 86.9% |
| GPT-5.5 | 0.90 | 0.39 | 0.0% | 89.3% |

*Note.* ICC(2,1) uses all three runs as repeated measures. Run-pair MAE is averaged across the three run pairs.

Source manifests: `data/lab03-filmnow/results/stability/{gemini,gpt}/`.
