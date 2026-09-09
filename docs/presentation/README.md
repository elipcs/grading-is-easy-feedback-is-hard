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

## Theme

The HTML and PPTX decks reuse the CBSoft'26 talk template: `#efeee7` paper,
`#2b2c30` ink, [Playfair Display](https://fonts.google.com/specimen/Playfair+Display)
for prose and display type, [Public Sans](https://fonts.google.com/specimen/Public+Sans)
for the tracked-out kickers and small print, a hairline under each kicker, and
the slide number alone in the bottom-right corner — unnumbered on the title
slide, so the count starts at 1 on the slide after it.

Neither font is embedded, so install both locally for an exact match; without
them the deck falls back to Georgia and Helvetica and keeps its proportions.
Diagrams and tables stay monospaced in every target, because their columns are
aligned by hand and reflow destroys them.

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
| `h` | hide the presenter strip |
| `f` | fullscreen |

The presenter strip at the foot shows the current slide, its target window and
elapsed time; `h` hides it if you are mirroring rather than presenting. The
clock turns amber once you pass the current slide's end time and red past eight
minutes. Slide numbers are in the URL fragment, so `slides.html#5` opens slide
five directly. Printing gives one slide per page, so browser print-to-PDF is a
working PDF export.

Each slide sizes its own body text: a script measures the content and picks the
largest font that fits both the height and the 72-column monospace width, so the
deck fills whatever projector it lands on instead of assuming 16:9.

**PPTX** is for when the venue insists on PowerPoint. It shares the palette and
the kicker treatment, and the speaker script is in the notes pane of each slide.
Its body is monospaced throughout, not just for the diagrams: PowerPoint has no
equivalent of the HTML auto-fitter, so one predictable metric keeps every slide
inside its margins. If you restyle it, keep the body monospaced.

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

A block can also carry a `role`, which is how the same source feeds a terminal
and a themed deck. `banner` marks ASCII art the HTML and PPTX skip in favour of
real type; `title` is the reverse, a display line the ASCII deck skips because
the banner already spells it out. `kicker`, `credit` and `punch` pick out the
tracked-out uppercase lines, the small print and an emphasised closing line.

Changing a slide's `start`/`end` re-budgets its script automatically, but the
windows must stay contiguous and still add up to 480 seconds.

The 13-second reproduction claim on slide 10 is machine-specific. Re-measure
before presenting:

```bash
time python3 src/reproduce.py && git diff --stat
```
