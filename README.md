# Grading Is Easy, Feedback Is Hard

Research artifact for the paper *Grading Is Easy, Feedback Is Hard: Evaluating LLMs for Design-Oriented OOP Assessment* (SBES 2026 / CBSoft 2026).

This package reproduces the analyses comparing two LLMs as instructor-support tools for rubric-based assessment of a design-oriented OOP assignment (FilmNow), using 84 anonymized Java submissions (`S01`--`S84`).

| | |
| --- | --- |
| **PDF** | [`docs/Grading_Is_Easy_Feedback_Is_Hard.pdf`](docs/Grading_Is_Easy_Feedback_Is_Hard.pdf) |
| **DOI** | [10.5281/zenodo.21385431](https://doi.org/10.5281/zenodo.21385431) |
| **Cite** | [`CITATION.cff`](CITATION.cff) |
| **License** | [CC BY 4.0](LICENSE) |

## What is reproduced

- **RQ1 — grade concordance:** model grades vs expert reference (contextualized by TA grades)
- **RQ2 — diagnostic accuracy:** model-reported issues vs expert annotations (semantic matching)
- **Stability:** three grading runs per model

Models: GPT-5.5 (`gpt55`) and Gemini 3.1 Pro Preview (`gemini31pro`), both at temperature 0 with high reasoning effort.

## Requirements

### Software

- **Python** 3.10 or newer
- Dependencies listed with explicit version lower bounds in [`requirements.txt`](requirements.txt) (NumPy, pandas, SciPy, Matplotlib, Plotly, and optional LLM clients for API re-runs)
- A standard Unix-like shell or Windows with PowerShell / Command Prompt
- **Operating systems tested / supported:** macOS, Linux, and Windows (via `python -m venv`)
- **No Docker or virtual machine is required** for the default offline reproduction path

API keys are **not** needed for the default reproduction path (`python3 src/reproduce.py`). The optional `--with-apis` path requires OpenAI and/or Gemini credentials (see [`.env.example`](.env.example)).

### Hardware

- **CPU:** any contemporary multi-core CPU is sufficient for the default offline path
- **RAM:** at least 4 GB available (8 GB recommended when regenerating figures)
- **Disk:** at least **250 MB** free for the package (~233 MB on disk: ~131 MB under `data/`, plus code, docs, and a Python virtualenv)

No GPUs, special peripherals, or unconventional hardware are required.

### Storage and data notes

The bundled anonymized grading runs and analysis outputs under `data/lab03-filmnow/` are required for offline replication. Plan on ~250 MB free space after unpacking or cloning. See [Privacy](#privacy) for ethical constraints on what is (and is not) included.

## Installation

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python3 -m pip install -r requirements.txt
```

### Verify installation

Confirm that the core analysis stack imports successfully:

```bash
python3 -c "import pandas, numpy, matplotlib, scipy; print('installation-ok')"
```

**Expected output:**

```text
installation-ok
```

If this command fails, re-check the Python version (3.10+) and re-run `pip install -r requirements.txt` inside the activated virtualenv.

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

Submission IDs are anonymous (`S01`--`S84`). Raw student repositories, identity mappings, API keys, and raw API traces are not included. The released data support replication of the reported analyses without exposing student identities or private institutional records.

## Further reading

| Path | Contents |
| --- | --- |
| [`docs/PAPER_ASSETS.md`](docs/PAPER_ASSETS.md) | Figures and supplementary tables |
| [`docs/figures/`](docs/figures/) | Figure assets |
| [`docs/tables/`](docs/tables/) | Table assets |
