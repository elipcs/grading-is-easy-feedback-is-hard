# Artifacts Festival talk (8 minutes)

Presentation material for *Grading Is Easy, Feedback Is Hard* at the SBES 2026 /
CBSoft 2026 Artifacts Festival. Eleven slides over an eight-minute slot.

## Layout

`deck.py` is the single source of truth: slide content, time windows and the
spoken script all live there. `render.py` turns it into every deliverable, so
the four generated files below always agree with each other.

| File | Role |
| --- | --- |
| [`deck.py`](deck.py) | Source: slides, timings, script, question prep |
| [`render.py`](render.py) | Renders every target; validates before writing |
| [`slides.txt`](slides.txt) | Generated: 78-column ASCII deck, form-feed separated |
| [`slides.html`](slides.html) | Generated: self-contained deck with notes and timer |
| [`slides.pptx`](slides.pptx) | Generated: 16:9 deck, script in the speaker notes |
| [`speaker_script.md`](speaker_script.md) | Generated: timed script, cut list, Q&A |

## Rendering

```bash
python3 -m pip install -r docs/presentation/requirements.txt   # python-pptx
python3 docs/presentation/render.py                            # all four files
```

Individual targets: `--ascii`, `--html`, `--pptx`, `--script`. Only `--pptx`
needs the dependency; the other three run on the standard library alone.

`render.py` validates before it writes anything, and fails the build when a body
line overflows the 72-column text field, when a slide's spoken script drifts more
than 12 words from its time budget, when slide windows are not contiguous, or
when the deck no longer totals eight minutes. Use `--check` to validate without
writing and `--budget` to print the per-slide word table:

```bash
python3 docs/presentation/render.py --check --budget
```

## Presenting

**HTML** is the one to use in the room. Open `slides.html` in any browser; it
needs no server and no network.

| Key | Action |
| --- | --- |
| arrows, space, click | next / previous slide |
| `s` | toggle speaker notes |
| `t` | start or pause the talk timer |
| `r` | reset the timer |
| `f` | fullscreen |

The footer shows the current slide, its target window, and elapsed time. The
clock turns amber once you pass the current slide's end time and red past eight
minutes. Slide numbers are in the URL fragment, so `slides.html#5` opens slide
five directly. Printing gives one slide per page, so browser print-to-PDF is a
working PDF export.

**PPTX** is for when the venue insists on PowerPoint. The speaker script is in
the notes pane of each slide. Body text is Courier New because the slides
contain ASCII tables and diagrams that break in a proportional font — if you
restyle the deck, keep the body monospaced.

**ASCII** is for presenting from a terminal. Slides are separated by form feeds:

```bash
awk 'BEGIN { RS = "\f" } { system("clear"); printf "%s", $0; getline _ < "/dev/tty" }' \
  docs/presentation/slides.txt
```

That needs a monospaced font and at least 78 columns; prefer 90+ if the
projector allows it.

## Editing

Edit `deck.py` and re-render. Body blocks come in three kinds: `Pre` for
verbatim monospace (diagrams, trees, tables, kept within 72 columns), `Para`
for prose, and `Bullets` for lists. Each slide also carries its `script`,
an optional presenter-only `delivery` cue, and an optional line to add only
when you are ahead of the clock.

Changing a slide's `start`/`end` re-budgets its script automatically, but the
windows must stay contiguous and still add up to 480 seconds.

The 13-second reproduction claim on slide 10 is machine-specific. Re-measure
before presenting:

```bash
time python3 src/reproduce.py && git diff --stat
```
