# Artifacts Festival talk (8 minutes)

Presentation material for *Grading Is Easy, Feedback Is Hard* at the SBES 2026 /
CBSoft 2026 Artifacts Festival.

| File | Contents |
| --- | --- |
| [`slides.txt`](slides.txt) | 10 ASCII slides, 78 columns, pure 7-bit ASCII |
| [`speaker_script.md`](speaker_script.md) | Timed script, cut list, question prep |
| [`build_slides.py`](build_slides.py) | Regenerates `slides.txt` with padded columns |

## Presenting

Slides are separated by form feeds (`\f`), so any pager that honours them works.
This one-liner clears the screen and advances on Enter:

```bash
awk 'BEGIN { RS = "\f" } { system("clear"); printf "%s", $0; getline _ < "/dev/tty" }' \
  docs/presentation/slides.txt
```

Requirements for the room: a monospaced font and at least 78 columns. At 80
columns the borders sit flush against the screen edge, so prefer 90+ if the
projector allows it.

To read it straight through instead:

```bash
less docs/presentation/slides.txt
```

## Timing

Ten slides over eight minutes, at roughly 145 words per minute. Each slide
carries its own window in the top-right corner, so you can tell at a glance
whether you are ahead or behind. `speaker_script.md` has a prioritized cut list
for when you are running long.

## Editing the slides

`slides.txt` is generated. Edit the slide content in `build_slides.py` and
re-render it:

```bash
python3 docs/presentation/build_slides.py
```

The generator pads every line to exactly 78 columns and fails loudly if a line
of body text exceeds the 72-character text field, so misalignment cannot reach
the deck silently. If you do edit `slides.txt` by hand, re-check it:

```bash
python3 - <<'PY'
from pathlib import Path
text = Path("docs/presentation/slides.txt").read_text(encoding="ascii")
bad = [n for n, line in enumerate(text.split("\n"), 1)
       if line.startswith(("|", "+")) and len(line) != 78]
print("misaligned lines:", bad or "none")
PY
```

The claim on slide 09 — 13 seconds, tables byte-identical — is machine-specific.
Re-measure before presenting:

```bash
time python3 src/reproduce.py && git diff --stat
```
