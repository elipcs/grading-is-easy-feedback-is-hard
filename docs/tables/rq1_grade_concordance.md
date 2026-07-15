# RQ1: Grade Concordance (Paper Table)

Grade concordance with the expert reference (84 submissions; 252 repeated observations per LLM).
Bias is evaluator grade minus expert grade.

| Evaluator | Mean grade | MAE | RMSE | Bias | Median AE | Within ±1 | Within ±2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TA (operational baseline) | 8.85 | 0.45 | 0.63 | +0.13 | 0.38 | 91.7% | 98.8% |
| Gemini 3.1 Pro | 8.85 | 0.44 | 0.67 | +0.14 | 0.30 | 92.5% | 96.8% |
| GPT-5.5 | 7.26 | 1.48 | 1.67 | -1.45 | 1.38 | 27.4% | 81.0% |

*Note.* LLM MAE averages run-level absolute errors within each submission before aggregating over submissions; RMSE is over all 252 run-level observations.
