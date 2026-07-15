# Artifact Package: Grading Is Easy, Feedback Is Hard

Research artifact for the paper **Grading Is Easy, Feedback Is Hard: Evaluating LLMs for Design-Oriented OOP Assessment**.

**SBES Artifact Festival badges targeted:** Available + Functional.

The package supports replication of the reported analyses of two Large Language Models (LLMs) as instructor-support tools for rubric-based assessment of a design-oriented Object-Oriented Programming (OOP) assignment (FilmNow), using 84 anonymized Java submissions (`S01`--`S84`).

## Paper

- **Title:** Grading Is Easy, Feedback Is Hard: Evaluating LLMs for Design-Oriented OOP Assessment
- **Venue:** SBES 2026 (CBSoft 2026)
- **PDF:** [`docs/Grading_Is_Easy_Feedback_Is_Hard.pdf`](docs/Grading_Is_Easy_Feedback_Is_Hard.pdf)
- **DOI:** to be added upon publication
- **How to cite:** see [`CITATION.cff`](CITATION.cff)

## What This Artifact Reproduces

- **RQ1 (grade concordance):** model grades vs expert reference, contextualized by operational TA grades.
- **RQ2 (diagnostic accuracy):** model-reported issues vs expert-annotated issues via semantic matching.
- **Stability:** three repeated grading runs per model for multi-run summaries and run-to-run variability.

Models:

- `gpt55`: GPT-5.5, temperature 0, high reasoning effort.
- `gemini31pro`: Gemini 3.1 Pro Preview, temperature 0, high reasoning effort.

## Repository Layout

```text
.
├── LICENSE
├── README.md
├── CITATION.cff
├── requirements.txt
├── .env.example
├── src/
│   ├── reproduce.py
│   ├── pipeline/
│   ├── workflows/
│   └── prompt/
├── data/
│   └── lab03-filmnow/
│       ├── runs/                 # per-model grading runs (run1..run3)
│       ├── results/              # benchmark / stability / by_category
│       └── study/                # three-run study manifests
└── docs/
    ├── Grading_Is_Easy_Feedback_Is_Hard.pdf
    ├── PAPER_ASSETS.md           # appendix: figures and supplementary tables
    ├── figures/
    └── tables/
```

### Study data (`data/lab03-filmnow/`)

```text
data/lab03-filmnow/
├── runs/
│   ├── gemini31pro/run{1,2,3}/
│   └── gpt55/run{1,2,3}/
├── results/
│   ├── benchmark/
│   ├── stability/{gemini,gpt}/
│   └── by_category/
└── study/
    ├── gemini31pro.json
    └── gpt55.json
```

Each run directory contains:

```text
experiment_config.json
inputs/                 # assignment, manifests, anonymized submissions
prompts/rendered/
outputs/                # gold_standard, human (TA), llm, consolidated
analyses/               # metrics, semantic caches, overlap reports
```

| Path | Role |
| --- | --- |
| `runs/*/run1` | Baseline grading run |
| `runs/*/run{2,3}` | Repeated grading runs |
| `results/benchmark/` | Canonical three-run benchmark |
| `results/stability/` | Run-to-run stability |
| `results/by_category/` | Single-run cross-model benchmark and category breakdown |

Figures: [`docs/figures/`](docs/figures/). Tables: [`docs/tables/`](docs/tables/). Index: [`docs/PAPER_ASSETS.md`](docs/PAPER_ASSETS.md).

## Requirements

**Software**

- Python **3.10** or later (smoke-tested with **Python 3.14**)
- `pip`
- macOS, Linux, or Windows (WSL recommended on Windows)

**API keys**

- Not required for the local path (`python3 src/reproduce.py`).
- Required only to optionally re-run LLM grading or rebuild missing semantic-matching caches (see `.env.example`).

**Python packages** (see `requirements.txt`):

```text
matplotlib>=3.8
numpy>=1.26
pandas>=2.2
plotly>=5.20
scipy>=1.12
python-dotenv>=1.0
requests>=2.31
openai>=1.12
google-generativeai>=0.4
google-genai>=0.1.0
pydantic>=2.6
```

## Quick Start (Functional)

Checklist for the Functional badge:

1. **Install:** create a venv and `pip install -r requirements.txt`
2. **Reproduce:** run `python3 src/reproduce.py`
3. **Compare:** open `data/lab03-filmnow/results/benchmark/paper_benchmark.md` and match MAE / precision / recall to the table below

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python3 -m pip install -r requirements.txt
python3 src/reproduce.py
```

Local extras (triangulation + single-run / twelve-category benchmark under `results/by_category/`):

```bash
python3 src/reproduce.py --extra
```

Optional API re-run (outputs may differ from the paper):

```bash
cp .env.example .env   # set OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY
python3 src/reproduce.py --with-apis
python3 src/reproduce.py --with-apis --limit 2   # smoke test
```

### Manual equivalent

```bash
python3 src/pipeline/17_multi_run_paper_analysis.py \
  --output-dir data/lab03-filmnow/results/benchmark

python3 src/pipeline/16_analyze_determinism.py \
  --study-manifest data/lab03-filmnow/study/gemini31pro.json \
  --output-dir data/lab03-filmnow/results/stability/gemini

python3 src/pipeline/16_analyze_determinism.py \
  --study-manifest data/lab03-filmnow/study/gpt55.json \
  --output-dir data/lab03-filmnow/results/stability/gpt

python3 src/pipeline/generate_paper_figures.py \
  --benchmark data/lab03-filmnow/results/benchmark/paper_benchmark.json \
  --output-dir docs/figures
```

### Expected confirmation

1. Under `data/lab03-filmnow/results/benchmark/`:
   - `paper_benchmark.json`
   - `paper_benchmark.md`
   - `paper_grade_per_run.csv`
   - `paper_detection_per_run.csv`
   - `paper_per_run_metrics.csv`
2. Under `data/lab03-filmnow/results/stability/{gemini,gpt}/`:
   - `determinism_benchmark.json` / `.md` / `.csv`
3. PNG figures under `docs/figures/`
4. Headline values in `paper_benchmark.md` (approximately):

| Model | Primary MAE | Conventional RMSE (252 obs.) | Precision | Recall |
| --- | ---: | ---: | ---: | ---: |
| Gemini 3.1 Pro Preview | 0.440 | 0.673 | 0.692 | 0.621 |
| GPT-5.5 | 1.476 | 1.669 | 0.519 | 0.962 |

## Optional Commands

```bash
python3 src/pipeline/05_validate_evaluations.py --experiment lab03-filmnow/runs/gpt55/run1
python3 src/pipeline/05_validate_evaluations.py --experiment lab03-filmnow/runs/gemini31pro/run1

python3 src/pipeline/09_triangular_analysis.py --experiment lab03-filmnow/runs/gpt55/run1
python3 src/pipeline/09_triangular_analysis.py --experiment lab03-filmnow/runs/gemini31pro/run1

python3 src/pipeline/10_model_benchmark.py \
  --condition gpt55=lab03-filmnow/runs/gpt55/run1 \
  --condition gemini31pro=lab03-filmnow/runs/gemini31pro/run1 \
  --output-dir data/lab03-filmnow/results/by_category
```

Local reproduction covers validation, grade concordance, triangulation, single-run and three-run benchmarks, paper figures, and inspection of prompts, rubrics, annotations, model outputs, and semantic caches. Re-running LLM assessments is optional and not required to verify the reported results.

## Privacy

Submission IDs are anonymous (`S01`--`S84`). Raw student repositories, private identity mappings, API keys, `outputs/raw_api/` traces, and Overleaf sources are not part of this package.

[`.gitignore`](.gitignore) excludes `.env`, `**/outputs/raw_api/`, private maps, archives, Overleaf folders, and `*.bak*` backups. When building a public ZIP or Zenodo deposit, confirm that a local `.env` is not included.

## License

This artifact is released under the **Creative Commons Attribution 4.0 International** license ([`LICENSE`](LICENSE) / [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)).

SPDX identifier: `CC-BY-4.0`

## Further Documentation

| Path | Contents |
| --- | --- |
| [`docs/Grading_Is_Easy_Feedback_Is_Hard.pdf`](docs/Grading_Is_Easy_Feedback_Is_Hard.pdf) | Paper PDF (bundled) |
| [`docs/PAPER_ASSETS.md`](docs/PAPER_ASSETS.md) | Appendix: paper figures and supplementary tables |
| [`docs/figures/`](docs/figures/) | Figure assets |
| [`docs/tables/`](docs/tables/) | Table assets (incl. twelve-category RQ2 detail) |
| [`CITATION.cff`](CITATION.cff) | Citation metadata |
