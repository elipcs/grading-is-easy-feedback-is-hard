# Artifacts Festival — 8-minute speaker script

Companion to [`slides.txt`](slides.txt). Ten ASCII slides, one per section below.
Target pace is roughly 145 words per minute; the spoken text is about 1,170
words, which lands on eight minutes with no slack. Rehearse it once against a
clock before the session.

| Slide | Window | Section |
| ---: | :--- | :--- |
| 01 | 00:00 – 00:35 | Title |
| 02 | 00:35 – 01:20 | Why this artifact exists |
| 03 | 01:20 – 02:05 | What is inside |
| 04 | 02:05 – 03:20 | The prompt: two stages |
| 05 | 03:20 – 04:20 | The prompt: the guardrails |
| 06 | 04:20 – 05:20 | How the study was run |
| 07 | 05:20 – 06:00 | Semantic adjudication |
| 08 | 06:00 – 06:50 | Results |
| 09 | 06:50 – 07:40 | Reproducing it |
| 10 | 07:40 – 08:00 | Takeaway |

---

## Slide 01 — Title · 00:00 – 00:35

Good morning. Our paper is called *Grading Is Easy, Feedback Is Hard*, and the
artifact I want to show you is the machinery behind that title.

It is a replication package for evaluating large language models as
instructor-support tools on a design-oriented object-oriented programming
assignment. Eighty-four real Java submissions, two models, a complete prompt
protocol, and every intermediate file.

It is on GitHub, archived on Zenodo, licensed CC BY. Everything I show in the
next seven minutes runs on your laptop without an API key.

> Delivery: say the title, then move on. Do not read the author list aloud.

---

## Slide 02 — Why this artifact exists · 00:35 – 01:20

First, why we needed an artifact at all.

In our OOP course students refactor a deliberately weak codebase, so correctness
and design pull apart. Submission A can pass every feature check while being one
four-hundred-line class with no domain objects. Submission B can have a single
off-by-one bug on top of a clean class model.

Unit tests and static analysis rank A above B. An instructor does not.

So this assessment stays manual: eighty-four submissions, seven rubric criteria
each, plus written feedback, spread across twenty-eight teaching assistants.

The obvious question is whether an LLM can help. The harder one is how you would
measure "help" at all. That measurement is what this artifact packages.

---

## Slide 03 — What is inside · 01:20 – 02:05

Here is what you get.

`src/prompt` is the grading protocol — eight files, and I would argue that is the
real contribution. `src/pipeline` and `src/workflows` are twenty-three scripts:
render prompts, call providers, validate outputs, compute statistics.
`src/reproduce.py` rebuilds the entire paper in one command, with no API keys.

Then the data: six run directories, two models times three repetitions. Each
holds the anonymized submissions, the rubric, one thousand and eight rendered
prompts — the exact bytes we sent — five hundred and four model assessments, the
TA grades, the expert reference and the per-run analyses.

Ten thousand lines of Python, a hundred and thirty megabytes of data, all
regenerable.

---

## Slide 04 — The prompt: two stages · 02:05 – 03:20

Now the prompt, because that is what people usually want to see. We split
grading into two calls, deliberately.

Stage one is scoring only — the prompt forbids student-facing prose here. The
model receives the assignment specification, the official grading reference, the
starter scaffold, the rubric as JSON, our course-level evaluation principles,
calibration examples, and the anonymized submission. For every rubric criterion
it must return a score, positive evidence of learning, observations that should
*not* cost points, and a list of deductions. Every deduction is structured:
points lost, severity, confidence, which rubric requirement it anchors to, the
problem, the consequence, how to fix it, and references into the code. Plus a
reviewer-audit block flagging what a human should double-check.

Only then does stage two turn that validated JSON into feedback. It is told not
to re-grade and not to look for new defects. It selects at most six
high-confidence items and writes them for a first-year student.

The split makes the two failure modes separable: when a grade is wrong, you can
point at the deduction that caused it.

Temperature zero, high reasoning effort, prompt version thirteen.

---

## Slide 05 — The prompt: the guardrails · 03:20 – 04:20

The templates are only half of it. The other half is the guardrails, and every
one of them exists because the model got something wrong without it.

We had to write, literally: do not convert optional improvements into point
loss — route them to a separate non-penalized observations list. Avoid double
jeopardy: if one root cause produces five symptoms, deduct once, on the
criterion it most affects. Do not penalize naming, formatting, casing or
punctuation. Here is the severity scale in actual points, because "moderate"
means nothing on its own. And if confidence is low, keep it out of the student's
feedback and log the omission for the reviewer.

The two JSON schemas are hard contracts, and the pipeline validates every single
response against them.

All of this is placeholder-based. Swap the rubric file and the specification, and
the protocol becomes your course's protocol.

---

## Slide 06 — How the study was run · 04:20 – 05:20

How the study was actually run, in three phases.

Phase one, inputs. Submissions are anonymized: author lines masked, repository
names replaced, identifiers reduced to S01 through S84. No raw student
repositories and no identity mapping ship in the artifact. The rubric is seven
criteria on a zero-to-ten scale — sixty percent core OOP and functionality,
forty percent tests and readability.

Phase two, evaluation. Three sources of judgement: the TA grades, which are the
authentic operational baseline; an expert reference, meaning rubric scores plus
three hundred sixty-one annotated issues over a twelve-category taxonomy; and
the LLM assessments — both models, stage one into stage two, three runs each,
five hundred and four assessments.

Phase three, the analyses for our two research questions, plus run-to-run
stability.

The detail I would highlight for reuse: every run directory is self-contained.
Config, inputs, the rendered prompt, the raw parse, the normalized output, and a
validation report.

---

## Slide 07 — Semantic adjudication · 05:20 – 06:00

One measurement was genuinely hard.

To ask whether the model found the *same* problem as the expert, string equality
is useless and taxonomy overlap is far too generous. Two evaluators describe one
encapsulation defect in completely different words.

So we used a third model, Claude Sonnet 5, as adjudicator — from a provider
family we were not evaluating, so neither model gets a home advantage. Matching
is scoped to one submission and one criterion, and allows subsumption.

That is model-assisted labelling, so we call it operational matching, not ground
truth. The prompt, the model identifier and every cache entry ship in the
artifact.

> Optional, if you are ahead of the clock: "and there is a sensitivity check —
> reversing ten adjudicated matches shifts precision and recall by under four
> hundredths."

---

## Slide 08 — Results · 06:00 – 06:50

The results, briefly.

On grades, Gemini essentially matches the human baseline: mean absolute error of
0.44 against the expert reference, where the TAs themselves sit at 0.45. GPT-5.5
systematically undergrades, with a bias of minus 1.45.

On diagnosis, the F1 scores are almost identical — 0.67 and 0.65 — and that
similarity hides completely opposite behaviour. GPT-5.5 finds nearly every
expert-annotated issue, recall 0.96, but about half of what it reports has no
expert equivalent. Gemini is much cleaner and misses over a third of the issues.

And stability: both models rank submissions consistently, ICC around 0.9, yet
exact agreement across three runs is two percent and zero percent.

Same aggregate F1, a different assessment instrument. That is the title.

---

## Slide 09 — Reproducing it · 06:50 – 07:40

So, reproducing it. Three commands: virtual environment, install requirements,
run reproduce.

No API keys, no Docker, no GPU; macOS, Linux and Windows. I re-checked on a
clean Ubuntu machine while preparing this talk: thirteen seconds end to end, and
every markdown table came back byte-identical to the paper. Only floating-point
last digits moved, inside the p-values.

`--extra` adds triangulation and category-level analyses. `--with-apis` re-runs
the models themselves — and we warn you there, because provider models drift, so
those numbers may not match ours.

To reuse it for your own course: replace the rubric and the specification, drop
your submissions in, and keep the prompt directory. That is the transferable
part.

---

## Slide 10 — Takeaway · 07:40 – 08:00

To close: we are not shipping a grader. We are shipping a way to measure one —
separately for grade calibration and for diagnostic coverage, on authentic
submissions, with repetitions, in one command.

Everything is on GitHub and archived on Zenodo. Thank you — happy to take
questions.

---

## If you are running long

Cut in this order. Each cut is self-contained and costs no continuity.

1. **Slide 02, the A/B example** (~20 s). Replace with: "correctness and design
   do not agree in this assignment, so grading stays manual."
2. **Slide 05, the severity scale and the low-confidence rule** (~15 s). Keep
   double jeopardy and the optional-improvements rule; those land best.
3. **Slide 06, phase one** (~15 s). The anonymization detail moves to Q&A.
4. **Slide 03, the byte counts** (~10 s). The directory tree is on the slide
   anyway.

Do not cut slide 04 or slide 09. The prompt structure and the one-command
reproduction are what the audience came for.

## If you are running short

Expand slide 05 with a concrete miss: GPT-5.5 kept reporting Javadoc phrasing
and naming inherited from the starter code as penalizable deductions, even
though the prompt routes optional improvements elsewhere. That is exactly why
the guardrail text ships in the artifact and not just in the paper.

Slide 08 also has room for submission S02: the expert deducted 3.5 points for an
off-by-one error on array access, Gemini caught it, and GPT-5.5 missed it
despite its higher aggregate recall. Aggregate profiles are tendencies, not
guarantees.

## Question prep

**Isn't using an LLM to judge LLM output circular?**
Partly, and we label it as operational matching rather than ground truth. Three
mitigations: the adjudicator comes from a third provider family, so it is not
grading its own vendor; matching is scoped to one submission and one criterion
at a time rather than free-form; and we ship the prompt, the model identifier
and every cache entry so you can audit or replace it. Independent human
validation of those decisions is future work.

**Why only one expert annotator?**
It is a stated threat to validity. The reference is structured validity evidence
for one consistent rubric application, not consensus ground truth. Multi-rater
references are explicitly future work.

**Why three runs?**
Three runs characterize output variability under a fixed protocol without
estimating the full distribution — enough to show that exact agreement across
runs is near zero, which was the finding we needed. We flag the limitation.

**Can I get the raw student repositories?**
No. The anonymized Java sources are included because they are prompt inputs, but
raw repositories, the identity mapping, API keys and raw API traces are not in
the package. Everything reported in the paper still replicates without them.

**Will `--with-apis` give me your numbers?**
Almost certainly not, and the script warns you. Commercial models change on the
provider side. The offline path is the verification path; the API path exists so
you can run the protocol on new models or your own data.

**Which model should I use for my course?**
That is the wrong question, and it is the argument of the paper. Decide the
workflow role first. If you want to audit grades, you want calibration. If you
want candidate issues for an instructor to filter, you want recall. Then pick.

**What did the runs cost, and how long did they take?**
We did not record cost or wall-clock time in the artifact, so I would rather not
guess. Runs two and three used the providers' batch APIs; the config in each run
directory has the request-rate settings we used.
