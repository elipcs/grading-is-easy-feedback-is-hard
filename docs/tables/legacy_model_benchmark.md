# Model Benchmark

RQ2 is recomputed at problem level from semantic matching caches. When multiple cache files contain the same submission/criterion key, the most complete entry is used. The unified taxonomy is used only for category breakdowns.

## RQ1: Grade Concordance

| condition | model | outputs | MAE | RMSE | bias | median abs. error | within ±1 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt55 | gpt-5.5 | 84 | 1.6043 | 1.7810 | -1.5984 | 1.4875 | 19.0% |
| gemini31pro | gemini-3.1-pro-preview | 84 | 0.5357 | 0.8047 | 0.0214 | 0.3375 | 88.1% |

## RQ2: Problem-Level Detection

| condition | model | expected problems | reported problems | matched reported | covered reference | FP | FN | precision | recall | F1 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt55 | gpt-5.5 | 361 | 666 | 346 | 346 | 320 | 15 | 0.5195 | 0.9584 | 0.6738 |
| gemini31pro | gemini-3.1-pro-preview | 361 | 326 | 223 | 223 | 103 | 138 | 0.6840 | 0.6177 | 0.6492 |

## RQ2: Paired Submission-Level Statistical Tests

Two-sided exact sign tests compare per-submission precision and recall between model conditions. Ties are reported but omitted from the exact binomial calculation.

| metric | comparison | compared submissions | left higher | right higher | ties | omitted | two-sided p-value |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| recall | gpt55 vs gemini31pro | 84 | 67 | 0 | 17 | 0 | 1.355e-20 |
| precision | gpt55 vs gemini31pro | 81 | 13 | 59 | 9 | 3 | 3.809e-08 |
