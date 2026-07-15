# Appendix: Paper Figures and Supplementary Tables

Viewer-facing copies of figures and tables from *Grading Is Easy, Feedback Is Hard*. For reproduction commands, see the repository root `README.md`.

**Paper PDF:** `[Grading_Is_Easy_Feedback_Is_Hard.pdf](Grading_Is_Easy_Feedback_Is_Hard.pdf)`

Canonical analysis outputs live under `data/lab03-filmnow/results/`.

## Omitted from PDF body

Assets commented out of the camera-ready LaTeX but retained here for reviewers:


| LaTeX label                  | Artifact path                                                                                                                                                    | Role                                                           |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `tab:rq2_issue_distribution` | `[tables/rq2_category_error_detail.md](tables/rq2_category_error_detail.md)`, `[tables/model_benchmark_by_category.csv](tables/model_benchmark_by_category.csv)` | Full twelve-category TP / FP / FN (run 1); RQ2 supplement      |
| `fig:rq1_bias_correlation`   | `[figures/fig_rq1_bias_correlation.png](figures/fig_rq1_bias_correlation.png)`, `[tables/rq1_bias_correlation.md](tables/rq1_bias_correlation.md)`               | Issue volume vs grade bias; RQ1 supplement                     |
| `tab:feedback_examples`      | `[tables/rq2_feedback_examples.md](tables/rq2_feedback_examples.md)`                                                                                             | Qualitative S01/S02 diagnostic examples; Discussion supplement |


Canonical regenerable source for the category table: `data/lab03-filmnow/results/by_category/`.

## Figures


| File                                                                                                 | Role in the paper              |
| ---------------------------------------------------------------------------------------------------- | ------------------------------ |
| `[figures/fig_rq1_grade_distribution.png](figures/fig_rq1_grade_distribution.png)`                   | RQ1 grade distributions        |
| `[figures/fig_rq1_error_distribution_by_model.png](figures/fig_rq1_error_distribution_by_model.png)` | Absolute grade errors          |
| `[figures/fig_rq1_model_grade_metrics.png](figures/fig_rq1_model_grade_metrics.png)`                 | Grade concordance metrics      |
| `[figures/fig_rq1_bias_correlation.png](figures/fig_rq1_bias_correlation.png)`                       | Issue volume vs grade bias     |
| `[figures/fig_rq2_model_detection_metrics.png](figures/fig_rq2_model_detection_metrics.png)`         | Precision, recall, and F1      |
| `[figures/fig_rq2_detection_counts_by_model.png](figures/fig_rq2_detection_counts_by_model.png)`     | Detection volume               |
| `[figures/fig_rq2_category_f1_by_model.png](figures/fig_rq2_category_f1_by_model.png)`               | Category-level F1              |
| `[figures/experimental_pipeline.tex](figures/experimental_pipeline.tex)`                             | Method pipeline (TikZ)         |
| `[figures/semantic_mapping.tex](figures/semantic_mapping.tex)`                                       | Semantic matching (TikZ)       |
| `[figures/two_stage_prompting.tex](figures/two_stage_prompting.tex)`                                 | Two-stage prompting (TikZ)     |
| `[figures/triangulation/](figures/triangulation/)`                                                   | Expert–TA–LLM comparison plots |


Regenerate RQ PNGs:

```bash
python3 src/pipeline/generate_paper_figures.py \
  --benchmark data/lab03-filmnow/results/benchmark/paper_benchmark.json \
  --output-dir docs/figures
```



## Tables


| File                                                                               | Role                                                              |
| ---------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `[tables/rq2_category_error_detail.md](tables/rq2_category_error_detail.md)`       | Category-level TP / FP / FN and P/R/F1 (run 1); omitted PDF table |
| `[tables/model_benchmark_by_category.csv](tables/model_benchmark_by_category.csv)` | Same data as CSV                                                  |
| `[tables/rq1_bias_correlation.md](tables/rq1_bias_correlation.md)`                 | Bias–issue correlation summary; omitted PDF figure companion      |
| `[tables/rq2_feedback_examples.md](tables/rq2_feedback_examples.md)`               | Qualitative diagnostic examples (S01/S02); omitted PDF table      |
| `[tables/rq1_grade_concordance.md](tables/rq1_grade_concordance.md)`               | RQ1 grade concordance                                             |
| `[tables/run_stability.md](tables/run_stability.md)`                               | Run-to-run stability                                              |
| `[tables/paper_benchmark.md](tables/paper_benchmark.md)`                           | Three-run paper summary                                           |
| `[tables/paper_grade_per_run.csv](tables/paper_grade_per_run.csv)`                 | Per-run grade metrics                                             |
| `[tables/paper_detection_per_run.csv](tables/paper_detection_per_run.csv)`         | Per-run detection metrics                                         |
| `[tables/legacy_model_benchmark.md](tables/legacy_model_benchmark.md)`             | Single-run RQ1/RQ2                                                |
| `[tables/model_statistical_tests.csv](tables/model_statistical_tests.csv)`         | Paired sign tests                                                 |
| `[tables/determinism_gemini.md](tables/determinism_gemini.md)`                     | Gemini stability report                                           |
| `[tables/determinism_gpt.md](tables/determinism_gpt.md)`                           | GPT-5.5 stability report                                          |


Source of truth for the category CSV: `data/lab03-filmnow/results/by_category/model_benchmark_by_category.csv`.