# RQ1: Issue Volume vs Grade Bias

Supplement for the figure omitted from the PDF body (`fig:rq1_bias_correlation`).

**Figure:** [`../figures/fig_rq1_bias_correlation.png`](../figures/fig_rq1_bias_correlation.png)

At the submission level, reported issue volume was negatively associated with grade bias (model grade − expert grade). Source correlations are from `data/lab03-filmnow/results/by_category/model_benchmark.json` (run 1 benchmark).

| Model | Pearson \(r\) | \(r^2\) | Mean reported issues / submission | Notes |
| --- | ---: | ---: | ---: | --- |
| GPT-5.5 | −0.55 | 0.31 | 8.0 | More issues; more often undergraded |
| Gemini 3.1 Pro | −0.54 | 0.29 | 3.9 | Fewer issues; closer to expert grades |

These descriptive associations do not establish that issue volume caused the observed grading behavior. Exact JSON values: GPT `pearson_r = -0.554…`, Gemini `pearson_r = -0.543…`.
