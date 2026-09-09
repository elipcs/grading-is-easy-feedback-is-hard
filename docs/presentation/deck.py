#!/usr/bin/env python3
"""Single source of truth for the Artifacts Festival talk.

`render.py` turns the ``SLIDES`` list below into four artifacts: the ASCII
deck, a self-contained HTML deck, a PPTX deck with the script in the speaker
notes, and the markdown speaker script. Edit content here, never in the
generated files.

Body blocks come in three flavours:

``Pre``       verbatim monospace; diagrams, trees and tables. Rendered as-is
              in every target, so keep lines within ``TEXT_WIDTH``.
``Para``      prose. Wrapped for ASCII, flowed as a paragraph elsewhere.
``Bullets``   list items. Rendered as ``.`` markers in ASCII.

Blocks may carry a ``role`` that changes how each target treats them:

``"banner"``  ASCII art shown only in the terminal deck; HTML and PPTX use
              real typography for the same thing instead.
``"title"``   the opposite: a display line for HTML and PPTX only.
``"kicker"``  tracked-out uppercase line under a title.
``"credit"``  small print, such as authors and DOIs.
``"punch"``   an emphasised closing line.

``Slide.script`` holds the spoken text. It is budgeted against the slide's own
time window at ``WORDS_PER_MINUTE``, and ``render.py`` fails the build if a
slide drifts more than ``WORD_TOLERANCE`` words away from its budget.
"""

from __future__ import annotations

from dataclasses import dataclass

TEXT_WIDTH = 72          # usable columns inside the ASCII slide frame
WORDS_PER_MINUTE = 145
WORD_TOLERANCE = 12


@dataclass(frozen=True)
class Pre:
    lines: list[str]
    role: str = ""


@dataclass(frozen=True)
class Para:
    text: str
    role: str = ""


@dataclass(frozen=True)
class Bullets:
    items: list[str]
    role: str = ""


Block = Pre | Para | Bullets

# The ASCII banner already spells the title out, so the display line is dropped.
ASCII_SKIP = frozenset({"title"})
# Roles the HTML and PPTX decks drop, because they set real type instead.
RICH_SKIP = frozenset({"banner"})


@dataclass(frozen=True)
class Slide:
    title: str
    start: int                      # seconds into the talk
    end: int
    blocks: list[Block]
    script: list[str]               # spoken paragraphs
    kind: str = "content"           # "title" gets centred styling
    delivery: str = ""              # presenter-only cue, never spoken
    optional: str = ""              # say it only if ahead of the clock

    @property
    def seconds(self) -> int:
        return self.end - self.start

    @property
    def word_budget(self) -> int:
        return round(self.seconds / 60 * WORDS_PER_MINUTE)

    @property
    def spoken_words(self) -> int:
        return sum(len(p.split()) for p in self.script)

    @property
    def window(self) -> str:
        return f"{_clock(self.start)} - {_clock(self.end)}"


def _clock(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# --------------------------------------------------------------------------
# Slides
# --------------------------------------------------------------------------

SLIDES: list[Slide] = [
    Slide(
        title="GRADING IS EASY, FEEDBACK IS HARD",
        start=0,
        end=30,
        kind="title",
        blocks=[
            Pre([
                r"   ___             _ _             _      ___",
                r"  / __|_ _ __ _ __| (_)_ _  __ _  (_)___ | __|__ _ ____  _",
                r" | (_ | '_/ _` / _` | | ' \/ _` | | (_-< | _|/ _` (_-< || |_",
                r"  \___|_| \__,_\__,_|_|_||_\__, | |_/__/ |___\__,_/__/\_, ( )",
                r"                           |___/                      |__/|/",
                r"  ___           _ _             _     _      _  _             _",
                r" | __|__ ___ __| | |__  __ _ __| |__ (_)___ | || |__ _ _ _ __| |",
                r" | _/ -_) -_) _` | '_ \/ _` / _| / / | (_-< | __ / _` | '_/ _` |",
                r" |_|\___\___\__,_|_.__/\__,_\__|_\_\ |_/__/ |_||_\__,_|_| \__,_|",
            ], role="banner"),
            Para("Grading Is Easy, Feedback Is Hard", role="title"),
            Para("Evaluating LLMs for Design-Oriented OOP Assessment", role="kicker"),
            Para("Research artifact  .  SBES 2026 / CBSoft 2026  .  Artifacts Festival",
                 role="credit"),
            Para("Eli P. C. Silva  .  Eliane C. Araujo  .  Everton L. G. Alves",
                 role="credit"),
            Para("Universidade Federal de Campina Grande, Brazil", role="credit"),
            Para("github.com/elipcs/grading-is-easy-feedback-is-hard", role="credit"),
            Para("DOI 10.5281/zenodo.21385431  .  License CC BY 4.0", role="credit"),
        ],
        delivery="Say the title, then move on. Do not read the author list aloud.",
        script=[
            "Good morning. Our paper is called Grading Is Easy, Feedback Is Hard, "
            "and what I am presenting today is the artifact behind it.",

            "It is a replication package: eighty-four real Java submissions from an "
            "object-oriented programming course, two models, a complete prompt "
            "protocol, and every intermediate file we produced, down to the exact "
            "bytes we sent to each provider.",

            "Everything I show runs on your laptop, without an API key, in one "
            "command.",
        ],
    ),

    Slide(
        title="THE PAPER BEHIND THE ARTIFACT",
        start=30,
        end=80,
        blocks=[
            Para("The paper is an evaluation protocol for LLM-assisted assessment of "
                 "design-oriented OOP assignments. The artifact is that protocol, "
                 "made runnable."),
            Pre([
                "  a single score merges two capabilities the paper keeps apart:",
                "",
                "  +-------------------------------+  +-------------------------------+",
                "  |  GRADE CONCORDANCE            |  |  DIAGNOSTIC ALIGNMENT         |",
                "  |                               |  |                               |",
                "  |  does the score match the     |  |  does it name the same        |",
                "  |  human baseline?              |  |  problems an expert found?    |",
                "  +-------------------------------+  +-------------------------------+",
                "",
                "     measured separately, against human references, on the same",
                "     submissions, under one fixed prompt protocol",
            ]),
            Para("Same assignment, same rubric, same prompt structure, same output "
                 "schema, for every model and every repetition."),
            Para("Grading is easy. Feedback is hard.", role="punch"),
        ],
        delivery="This is the only paper slide. Do not drift into results.",
        script=[
            "One slide on the paper this comes from, and then we stay on the "
            "artifact.",

            "The paper is an evaluation protocol for using language models to assess "
            "design-oriented object-oriented programming assignments. This artifact "
            "is that protocol, made runnable.",

            "Its central claim is that one aggregate score merges two capabilities "
            "that behave differently. Grade concordance asks whether the score "
            "matches the human baseline. Diagnostic alignment asks whether the model "
            "names the same problems an expert found.",

            "We measure them separately, against human references, on the same "
            "submissions, under one fixed prompt protocol, so that the two can never "
            "be blurred into a single number.",

            "The title gives away what we found. I am here for the machinery behind "
            "that sentence, not for the numbers.",
        ],
        optional="Both dimensions are measured per submission and per rubric "
                 "criterion, never as a single headline score.",
    ),

    Slide(
        title="WHY THIS ARTIFACT EXISTS",
        start=80,
        end=125,
        blocks=[
            Para("In a design-oriented OOP assignment, correctness and design do not always agree:"),
            Pre([
                "  submission A   every feature works   ->  one 400-line class,",
                "                                            no domain objects",
                "",
                "  submission B   one off-by-one bug    ->  clean class modeling,",
                "                                            responsibilities split",
            ]),
            Para("Unit tests and static analysis rank A above B. An instructor does not."),
            Para("So this kind of assessment stays manual:"),
            Pre([
                "  84 submissions  x  7 rubric criteria  x  written feedback",
                "  graded by 28 teaching assistants, 1 to 6 submissions each",
            ]),
            Para('Can an LLM help here?  And how would we measure "help" at all?'),
        ],
        script=[
            "First, why we needed an artifact at all.",

            "In our OOP course students refactor a deliberately weak codebase, so "
            "correctness and design pull apart. Submission A can pass every feature "
            "check while being one four-hundred-line class with no domain objects. "
            "Submission B can have a single off-by-one bug on top of a clean class "
            "model.",

            "Unit tests and static analysis rank A above B. An instructor does not.",

            "So this assessment stays manual: eighty-four submissions, seven rubric "
            "criteria each, plus written feedback, across twenty-eight teaching "
            "assistants.",

            "The obvious question is whether an LLM can help. The harder one is how "
            'you would measure "help" at all.',
        ],
    ),

    Slide(
        title="WHAT IS INSIDE THE ARTIFACT",
        start=125,
        end=160,
        blocks=[
            Pre([
                ".",
                "|-- src/prompt/            8 files     the grading protocol itself",
                "|-- src/pipeline/         18 scripts   render, run, validate, analyse",
                "|-- src/workflows/         5 scripts   stage orchestration",
                "|-- src/reproduce.py       1 command   the whole paper, no API keys",
                "|-- data/lab03-filmnow/",
                "|   |-- runs/              6 runs      2 models x 3 repetitions",
                "|   |     inputs/          84 anonymized Java submissions + rubric",
                "|   |     prompts/         1008 rendered prompts, the exact bytes sent",
                "|   |     outputs/         504 LLM assessments + TA + expert reference",
                "|   |     analyses/        per-run metrics + semantic-match caches",
                "|   |-- results/           benchmark, stability, by_category",
                "|   `-- study/             three-run manifests",
                "`-- docs/                  paper PDF, 13 figures, 13 tables, 3 TikZ",
            ]),
            Para("~10k lines of Python  .  132 MB of data  .  all of it regenerable"),
        ],
        script=[
            "Here is what you get.",

            "src/prompt is the grading protocol - eight files, and I would argue that "
            "is the real contribution. src/pipeline and src/workflows are "
            "twenty-three scripts: render prompts, call providers, validate outputs, "
            "compute statistics. And reproduce.py rebuilds the entire paper in one "
            "command.",

            "Then the data: six run directories, two models times three repetitions. "
            "Each holds the anonymized submissions, the rubric, one thousand and "
            "eight rendered prompts - the exact bytes we sent - five hundred and four "
            "model assessments, the TA grades and the expert reference.",
        ],
    ),

    Slide(
        title="THE PROMPT (1/3): TWO STAGES, ON PURPOSE",
        start=160,
        end=225,
        blocks=[
            Pre([
                "  assignment spec + official grading reference + starter scaffold",
                "  + rubric.json + course principles + calibration examples",
                "  + anonymized submission package",
                "                         |",
                "                         v",
                "  +--------------------------------------+",
                '  |  STAGE 1  -  SCORING                 |   "analytical scoring',
                "  |    per rubric criterion:             |    only, no student-",
                '  |      score / max_score               |    facing prose here"',
                "  |      success_evidence[]              |",
                "  |      non_penalized_observations[]    |",
                "  |      deductions[]                    |",
                "  |        points_lost, severity,        |",
                "  |        confidence, rubric_anchor,    |",
                "  |        problem, consequence,         |",
                "  |        how_to_fix, evidence_refs     |",
                "  |    reviewer_audit                    |",
                "  +--------------------------------------+",
                "                         |  validated JSON",
                "                         v",
                "  +--------------------------------------+",
                '  |  STAGE 2  -  FEEDBACK                |   "do not re-grade and',
                "  |    at most 6 high-confidence items   |    do not look for new",
                '  |    student_feedback + reviewer_notes |    defects"',
                "  +--------------------------------------+",
            ]),
            Para("prompt_version v13-two-stage  .  temperature 0  .  high reasoning effort"),
        ],
        script=[
            "Now the prompt, because that is what people usually want to see. We "
            "split grading into two calls, deliberately.",

            "Stage one is scoring only - the prompt forbids student-facing prose "
            "here. For every rubric criterion the model must return a score, "
            "positive evidence of learning, observations that should not cost "
            "points, and a list of deductions. Every deduction is structured: points "
            "lost, severity, confidence, which rubric requirement it anchors to, the "
            "problem, the consequence, how to fix it, and references into the code. "
            "Plus a reviewer-audit block flagging what a human should double-check.",

            "Only then does stage two turn that validated JSON into feedback. It is "
            "told not to re-grade and not to look for new defects. It selects at most "
            "six high-confidence items and writes them for a first-year student.",

            "The split makes the two failure modes separable: when a grade is wrong, "
            "you can point at the deduction that caused it.",
        ],
    ),

    Slide(
        title="THE PROMPT (2/3): DYNAMIC INJECTION",
        start=225,
        end=285,
        blocks=[
            Para(
                "Nothing in src/prompt/ is a finished prompt. Every file is a "
                "template with {{PLACEHOLDER}} slots, filled at two distinct moments."
            ),
            Pre([
                "BUILD TIME  --  src/pipeline/02_render_prompts.py",
                "  {{EXPERIMENT_METADATA}}       per-submission JSON: id, role,",
                "                                provider, model, temperature,",
                "                                reasoning_effort, prompt_version",
                "  {{LAB_SPEC_TEXT}}             <- assignment/lab_specification.md",
                "  {{GRADING_SHEET_TEXT}}        <- assignment/grading_reference.md",
                "  {{STARTER_SCAFFOLD_TEXT}}     <- assignment/starter_scaffold.md",
                "  {{RUBRIC_JSON}}               <- rubric.json, gated rubric_ready",
                "  {{CORE_EVALUATION_TEXT}}      <- evaluation_principles.md",
                "  {{ABSTRACT_CALIBRATION_TEXT}} <- abstract_calibration.md",
                "  {{COMMENT_STYLE_TEXT}}        <- feedback_style_guide.md  (st.2)",
                "  {{SUBMISSION_PACKAGE}}        <- submissions/S17.md",
                "  {{OUTPUT_SCHEMA_JSON}}        <- schema_stage{1,2}.json",
                "",
                "RUN TIME  --  src/pipeline/utils/llm_execution.py",
                "  {{STAGE1_JSON}}   left UNRESOLVED on disk on purpose, then swapped",
                "                    at call time for the parsed, re-serialized",
                "                    stage 1 response",
            ]),
            Pre([
                "  stage 1:  9 slots resolved   136-line template  ->  1753 lines",
                "  stage 2:  1 slot left open   grep the shipped file, it is there",
            ]),
            Para(
                "So stage 2 never sees raw model prose, only re-parsed JSON - and the "
                "1008 rendered files are the audit trail of what we actually sent."
            ),
        ],
        script=[
            "This is the part I would actually reuse, so let me be concrete. Nothing "
            "in that prompt directory is a finished prompt - they are templates with "
            "double-brace placeholders, filled at two distinct moments.",

            "At build time, the render script resolves nine slots for stage one: the "
            "specification, the grading reference, the starter scaffold, and the "
            "rubric - which is gated, so the script refuses to render if the rubric "
            "is not marked ready. Plus the course principles, the calibration "
            "examples and the schema. A hundred and thirty-six lines of template "
            "become a seventeen-hundred-line prompt.",

            "Stage two is the interesting one. One placeholder is deliberately left "
            "unresolved on disk; at call time the runner parses the stage one "
            "response, re-serializes it, and only then injects it.",

            "Two consequences. Stage two never sees raw model prose, only validated "
            "JSON. And since that substitution is the only non-static step, the "
            "prompts we ship are a faithful audit trail.",
        ],
    ),

    Slide(
        title="THE PROMPT (3/3): THE GUARDRAILS",
        start=285,
        end=335,
        blocks=[
            Pre([
                "src/prompt/",
                "  template_stage1.md          mandatory 7-step scoring procedure",
                "  template_stage2.md          feedback + reviewer-safety rules",
                "  evaluation_principles.md    course-level grading philosophy",
                "  abstract_calibration.md     worked decision examples",
                "  feedback_style_guide.md     tone, structure, jargon rules",
                "  ta_operational_baseline.md  how the human baseline was produced",
                "  schema_stage1.json          149-line JSON contract",
                "  schema_stage2.json           84-line JSON contract",
            ]),
            Para("Rules that exist because the model misbehaved without them:"),
            Pre([
                '  "Do not convert optional improvements into point loss"',
                "      ->  route them to non_penalized_observations[]",
                '  "Avoid double jeopardy: one root cause, one deduction"',
                '  "Do not penalize naming, formatting, casing or punctuation"',
                '  "minor .25-1.0 | moderate 1.0-2.5 | major 2.5-5 | blocking 5-10"',
                '  "If confidence is low, omit it from student feedback and',
                '   record the omission in reviewer_notes"',
            ]),
        ],
        script=[
            "The templates are only half of it. The other half is the guardrails, and "
            "every one of them exists because the model got something wrong without "
            "it.",

            "We had to write, literally: do not convert optional improvements into "
            "point loss - route them to a separate non-penalized observations list. "
            "Avoid double jeopardy: if one root cause produces five symptoms, deduct "
            "once, on the criterion it most affects. Do not penalize naming, "
            "formatting, casing or punctuation. Here is the severity scale in actual "
            "points, because moderate means nothing on its own. And if confidence is "
            "low, keep it out of the student's feedback and log the omission for the "
            "reviewer.",

            "The two JSON schemas are hard contracts, and the pipeline validates "
            "every single response against them.",
        ],
    ),

    Slide(
        title="HOW THE STUDY WAS RUN",
        start=335,
        end=380,
        blocks=[
            Pre([
                "PHASE 1  -  INPUTS",
                "  84 Java submissions, anonymized: author lines masked, repository",
                "  names replaced, identifiers reduced to S01..S84",
                "  official rubric: 7 criteria, 0-10, core 60% / supporting 40%",
                "",
                "PHASE 2  -  EVALUATION",
                "  TA grades .......... the operational human baseline, 28 TAs",
                "  expert reference ... rubric scores + 361 annotated issues",
                "                       over a 12-category taxonomy",
                "  LLM assessments .... Gemini 3.1 Pro and GPT-5.5, stage 1 -> 2,",
                "                       temperature 0, 3 runs each = 504 assessments",
                "",
                "PHASE 3  -  ANALYSIS",
                "  RQ1  grade concordance ... MAE, RMSE, bias, tolerance bands",
                "  RQ2  problem alignment ... precision, recall, F1",
                "  stability ................ ICC(2,1), run-pair MAE, exact agreement",
            ]),
            Para(
                "Each run directory is self-contained: experiment_config.json, "
                "inputs, the rendered prompt, raw parse, normalized output, "
                "validation report."
            ),
        ],
        script=[
            "How the study was actually run, in three phases.",

            "Phase one, inputs. Submissions are anonymized: author lines masked, "
            "repository names replaced, identifiers reduced to S01 through S84. No "
            "raw student repositories and no identity mapping ship in the artifact.",

            "Phase two, evaluation. Three sources of judgement: the TA grades, which "
            "are the authentic operational baseline; an expert reference, meaning "
            "rubric scores plus three hundred sixty-one annotated issues over a "
            "twelve-category taxonomy; and the LLM assessments - both models, three "
            "runs each, five hundred and four assessments.",

            "Phase three, the analyses for our two research questions, plus "
            "run-to-run stability.",

            "The detail I would highlight for reuse: every run directory is "
            "self-contained.",
        ],
    ),

    Slide(
        title="THE HARD MEASUREMENT: IS IT THE SAME PROBLEM?",
        start=380,
        end=420,
        blocks=[
            Para("String equality fails. Taxonomy overlap is too generous."),
            Pre([
                "  expert  (S17, class_modeling)     model  (S17, class_modeling)",
                '  "Filme has no encapsulation,      "attributes of Filme are public,',
                '   attributes are public"            information hiding is broken"',
                "                    \\                    /",
                "                     v                  v",
                "        +-----------------------------------------+",
                "        |  adjudicator: Claude Sonnet 5           |  a third",
                "        |  temperature 0, structured JSON out     |  provider",
                "        |  scoped to submission_id | criterion    |  family, so",
                "        |  subsumption + many-to-many allowed     |  no home-",
                "        +-----------------------------------------+  team bias",
                "                            |",
                "    covered_expert = TP   uncovered_expert = FN   unmatched_llm = FP",
            ]),
            Para(
                "The prompt, the model id and every cache entry ship in the artifact. "
                "Sensitivity check: reversing 10 decisions shifts P/R by under 0.04."
            ),
        ],
        optional="and there is a sensitivity check - reversing ten adjudicated "
                 "matches shifts precision and recall by under four hundredths.",
        script=[
            "One measurement was genuinely hard.",

            "To ask whether the model found the same problem as the expert, string "
            "equality is useless and taxonomy overlap is far too generous. Two "
            "evaluators describe one encapsulation defect in completely different "
            "words.",

            "So we used a third model, Claude Sonnet 5, as adjudicator - from a "
            "provider family we were not evaluating, so neither model gets a home "
            "advantage. Matching is scoped to one submission and one criterion.",

            "That is model-assisted labelling, so we call it operational matching, "
            "not ground truth. The prompt, the model identifier and every cache entry "
            "ship in the artifact.",
        ],
    ),

    Slide(
        title="REPRODUCE IT",
        start=420,
        end=465,
        blocks=[
            Pre([
                "  $ python3 -m venv .venv && source .venv/bin/activate",
                "  $ python3 -m pip install -r requirements.txt",
                "  $ python3 src/reproduce.py",
            ]),
            Para(
                "No API keys. No Docker. No GPU. Checked on a clean Ubuntu machine "
                "while preparing this talk: 13 seconds end to end, every markdown "
                "table byte-identical, only floating-point last digits moved inside "
                "the p-values."
            ),
            Pre([
                "  --extra                   + triangulation, by-category",
                "  --with-apis               re-run the LLMs (may differ)",
                "  --with-apis --limit 2     cheap smoke test",
            ]),
            Para("Reuse path for your own course:"),
            Pre([
                "  1. replace assignment/rubric.json and lab_specification.md",
                "  2. drop your submissions into inputs/submissions/",
                "  3. keep src/prompt/  -  that is the transferable part",
            ]),
        ],
        script=[
            "So, reproducing it. Three commands: virtual environment, install "
            "requirements, run reproduce.",

            "No API keys, no Docker, no GPU. I re-checked on a clean Ubuntu machine "
            "while preparing this talk: thirteen seconds end to end, and every "
            "markdown table came back byte-identical to the paper.",

            "There are flags for the triangulation analyses, and one to re-run the "
            "models themselves - and we warn you there, because provider models "
            "drift, so those numbers may not match ours.",

            "To reuse it for your own course: replace the rubric and the "
            "specification, drop your submissions in, and keep the prompt directory. "
            "That is the transferable part.",
        ],
    ),

    Slide(
        title="TAKEAWAY",
        start=465,
        end=480,
        blocks=[
            Para("We are not shipping a grader. We are shipping a way to measure one."),
            Bullets([
                "a two-stage prompt protocol with auditable JSON at every step",
                "placeholder templates: swap the rubric, swap the assignment",
                "grade concordance and diagnostic alignment measured separately",
                "84 real submissions, an expert reference, 3 runs per model",
                "one command, no keys, 13 seconds",
            ]),
            Para("Thank you.  Questions?", role="kicker"),
            Para("github.com/elipcs/grading-is-easy-feedback-is-hard", role="credit"),
            Para("DOI 10.5281/zenodo.21385431  .  License CC BY 4.0", role="credit"),
        ],
        script=[
            "To close: we are not shipping a grader. We are shipping a way to measure "
            "one - separately for grade calibration and for diagnostic coverage, on "
            "authentic submissions, in one command.",

            "Thank you - happy to take questions.",
        ],
    ),
]


# --------------------------------------------------------------------------
# Speaker-script appendices
# --------------------------------------------------------------------------

RUNNING_LONG = [
    "**Slide 03, the A/B example** (~20 s). Replace with: \"correctness and "
    "design do not agree in this assignment, so grading stays manual.\"",

    "**Slide 07, the severity scale and the low-confidence rule** (~15 s). Keep "
    "double jeopardy and the optional-improvements rule; those land best.",

    "**Slide 08, phase one** (~15 s). The anonymization detail moves to Q&A.",

    "**Slide 04, the byte counts** (~10 s). The directory tree is on the slide "
    "anyway.",
]

RUNNING_SHORT = [
    "Expand slide 07 with a concrete miss: GPT-5.5 kept reporting Javadoc "
    "phrasing and naming inherited from the starter code as penalizable "
    "deductions, even though the prompt routes optional improvements elsewhere. "
    "That is exactly why the guardrail text ships in the artifact and not just "
    "in the paper.",

    "Slide 06 has room for the failure mode the gate prevents: an unfinished "
    "rubric silently rendering into 84 prompts. `ensure_rubric_ready` turns that "
    "into a hard stop before a single API call is made.",

    "Slide 02 has room for why the two dimensions are kept apart in the first "
    "place: a single aggregate score lets a model look competent on grades while "
    "producing feedback an instructor cannot hand to a student. Splitting the "
    "measurement is the design decision the whole artifact is built around.",
]

QUESTIONS = [
    (
        "Isn't using an LLM to judge LLM output circular?",
        "Partly, and we label it as operational matching rather than ground "
        "truth. Three mitigations: the adjudicator comes from a third provider "
        "family, so it is not grading its own vendor; matching is scoped to one "
        "submission and one criterion at a time rather than free-form; and we "
        "ship the prompt, the model identifier and every cache entry so you can "
        "audit or replace it. Independent human validation is future work.",
    ),
    (
        "Why only one expert annotator?",
        "It is a stated threat to validity. The reference is structured validity "
        "evidence for one consistent rubric application, not consensus ground "
        "truth. Multi-rater references are explicitly future work.",
    ),
    (
        "Why three runs?",
        "Three runs characterize output variability under a fixed protocol "
        "without estimating the full distribution - enough to show that exact "
        "agreement across runs is near zero, which was the finding we needed. We "
        "flag the limitation.",
    ),
    (
        "Why inject the Stage 1 JSON at run time instead of rendering it in?",
        "Because Stage 1 output does not exist until Stage 1 has run, and it "
        "changes on every repetition. Rendering it in would make the prompt "
        "files run-specific. Leaving one placeholder open means the shipped "
        "prompts stay diffable across the six runs, and the only varying input "
        "is the JSON we also ship under outputs/.",
    ),
    (
        "Does the model ever see its own raw Stage 1 text?",
        "No. The runner parses the response and re-serializes it before "
        "substitution, so Stage 2 receives normalized JSON. If Stage 1 emits "
        "something unparseable, the run fails there rather than feeding prose "
        "into the feedback stage.",
    ),
    (
        "Can I get the raw student repositories?",
        "No. The anonymized Java sources are included because they are prompt "
        "inputs, but raw repositories, the identity mapping, API keys and raw "
        "API traces are not in the package. Everything reported in the paper "
        "still replicates without them.",
    ),
    (
        "Will `--with-apis` give me your numbers?",
        "Almost certainly not, and the script warns you. Commercial models "
        "change on the provider side. The offline path is the verification path; "
        "the API path exists so you can run the protocol on new models or your "
        "own data.",
    ),
    (
        "Which model should I use for my course?",
        "That is the wrong question, and it is the argument of the paper. Decide "
        "the workflow role first. If you want to audit grades, you want "
        "calibration. If you want candidate issues for an instructor to filter, "
        "you want recall. Then pick.",
    ),
    (
        "What did the runs cost, and how long did they take?",
        "We did not record cost or wall-clock time in the artifact, so I would "
        "rather not guess. Runs two and three used the providers' batch APIs; "
        "the config in each run directory has the request-rate settings we used.",
    ),
]

TOTAL_SECONDS = SLIDES[-1].end
