# RQ2: Diagnostic Category Distribution (Run 1)

Complete twelve-category distribution referenced by the paper.
Source CSV: [`model_benchmark_by_category.csv`](model_benchmark_by_category.csv).

Counts collapse repeated annotations to **binary presence** per submission–category pair.
Expert = annotated occurrences; Rep. = model-reported; TP/FP/FN after semantic matching.

| Category | Expert | GPT Rep. | GPT TP | GPT FP | GPT FN | Gemini Rep. | Gemini TP | Gemini FP | Gemini FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Class Modeling | 58 | 78 | 55 | 23 | 3 | 30 | 27 | 3 | 31 |
| List Validation | 48 | 81 | 48 | 33 | 0 | 64 | 45 | 19 | 3 |
| Responsibility Division | 34 | 74 | 33 | 41 | 1 | 46 | 26 | 20 | 8 |
| Readability / Docs | 33 | 82 | 33 | 49 | 0 | 22 | 14 | 8 | 19 |
| Array Usage | 33 | 61 | 28 | 33 | 5 | 31 | 22 | 9 | 11 |
| Output Format | 23 | 61 | 21 | 40 | 2 | 25 | 13 | 12 | 10 |
| HashCode / equals | 18 | 24 | 15 | 9 | 3 | 12 | 8 | 4 | 10 |
| String Comparison | 16 | 29 | 16 | 13 | 0 | 20 | 12 | 8 | 4 |
| Tests Missing | 78 | 84 | 78 | 6 | 0 | 40 | 39 | 1 | 39 |
| Other | 9 | 16 | 8 | 8 | 1 | 21 | 8 | 13 | 1 |
| Reference Usage | 8 | 60 | 8 | 52 | 0 | 10 | 7 | 3 | 1 |
| Input Handling | 3 | 16 | 3 | 13 | 0 | 5 | 2 | 3 | 1 |
| **Total** | **361** | **666** | **346** | **320** | **15** | **326** | **223** | **103** | **138** |

## Precision / Recall / F1 by category (Run 1)

| Category | GPT P | GPT R | GPT F1 | Gemini P | Gemini R | Gemini F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Class Modeling | 0.705 | 0.948 | 0.809 | 0.900 | 0.466 | 0.614 |
| List Validation | 0.593 | 1.000 | 0.744 | 0.703 | 0.938 | 0.804 |
| Responsibility Division | 0.446 | 0.971 | 0.611 | 0.565 | 0.765 | 0.650 |
| Readability / Docs | 0.402 | 1.000 | 0.574 | 0.636 | 0.424 | 0.509 |
| Array Usage | 0.459 | 0.848 | 0.596 | 0.710 | 0.667 | 0.688 |
| Output Format | 0.344 | 0.913 | 0.500 | 0.520 | 0.565 | 0.542 |
| HashCode / equals | 0.625 | 0.833 | 0.714 | 0.667 | 0.444 | 0.533 |
| String Comparison | 0.552 | 1.000 | 0.711 | 0.600 | 0.750 | 0.667 |
| Tests Missing | 0.929 | 1.000 | 0.963 | 0.975 | 0.500 | 0.661 |
| Other | 0.500 | 0.889 | 0.640 | 0.381 | 0.889 | 0.533 |
| Reference Usage | 0.133 | 1.000 | 0.235 | 0.700 | 0.875 | 0.778 |
| Input Handling | 0.188 | 1.000 | 0.316 | 0.400 | 0.667 | 0.500 |
