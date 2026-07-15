# Grading Is Easy, Feedback Is Hard

Research artifact for the paper *Grading Is Easy, Feedback Is Hard: Evaluating LLMs for Design-Oriented OOP Assessment* (SBES 2026 / CBSoft 2026).

This package reproduces the analyses comparing two LLMs as instructor-support tools for rubric-based assessment of a design-oriented OOP assignment (FilmNow), using 84 anonymized Java submissions (`S01`--`S84`).

| | |
| --- | --- |
| **PDF** | [`docs/Grading_Is_Easy_Feedback_Is_Hard.pdf`](docs/Grading_Is_Easy_Feedback_Is_Hard.pdf) |
| **Cite** | [`CITATION.cff`](CITATION.cff) |
| **License** | [CC BY 4.0](LICENSE) |

## What is reproduced

- **RQ1 — grade concordance:** model grades vs expert reference (contextualized by TA grades)
- **RQ2 — diagnostic accuracy:** model-reported issues vs expert annotations (semantic matching)
- **Stability:** three grading runs per model

Models: GPT-5.5 (`gpt55`) and Gemini 3.1 Pro Preview (`gemini31pro`), both at temperature 0 with high reasoning effort.

## Setup

Requires Python 3.10+ and the packages in [`requirements.txt`](requirements.txt). API keys are **not** needed for the default reproduction path.

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python3 -m pip install -r requirements.txt
```

## Reproduce

```bash
python3 src/reproduce.py
```

This rebuilds the paper benchmark, stability analyses, and figures from the bundled run data.

Optional:

```bash
python3 src/reproduce.py --extra          # triangulation + category-level benchmark
python3 src/reproduce.py --with-apis      # re-run LLM grading (needs API keys; results may differ)
```

Copy [`.env.example`](.env.example) to `.env` only if using `--with-apis`.

### Expected results

Headline metrics in `data/lab03-filmnow/results/benchmark/paper_benchmark.md`:

| Model | Primary MAE | Conventional RMSE (252 obs.) | Precision | Recall |
| --- | ---: | ---: | ---: | ---: |
| Gemini 3.1 Pro Preview | 0.440 | 0.673 | 0.692 | 0.621 |
| GPT-5.5 | 1.476 | 1.669 | 0.519 | 0.962 |

Outputs written under:

- `data/lab03-filmnow/results/benchmark/` — three-run paper benchmark
- `data/lab03-filmnow/results/stability/` — run-to-run stability
- `docs/figures/` — regenerated figures

## Layout

```text
.
├── src/reproduce.py          # one-command entry point
├── src/pipeline/             # analysis scripts
├── data/lab03-filmnow/
│   ├── runs/                 # per-model grading runs (run1..run3)
│   ├── results/              # benchmark, stability, by_category
│   └── study/                # three-run manifests
└── docs/
    ├── figures/
    ├── tables/
    └── PAPER_ASSETS.md       # figure/table index
```

Each run under `runs/*/run{1,2,3}/` holds experiment config, anonymized inputs, rendered prompts, LLM/human/gold outputs, and analyses.

## Privacy

Submission IDs are anonymous (`S01`--`S84`). Raw student repositories, identity mappings, API keys, and raw API traces are not included.

## Further reading

| Path | Contents |
| --- | --- |
| [`docs/PAPER_ASSETS.md`](docs/PAPER_ASSETS.md) | Figures and supplementary tables |
| [`docs/figures/`](docs/figures/) | Figure assets |
| [`docs/tables/`](docs/tables/) | Table assets |
