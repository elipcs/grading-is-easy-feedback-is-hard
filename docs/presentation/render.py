#!/usr/bin/env python3
"""Render the Artifacts Festival talk from `deck.py` into every target format.

    python3 docs/presentation/render.py              # all four artifacts
    python3 docs/presentation/render.py --ascii      # just slides.txt
    python3 docs/presentation/render.py --check      # validate, write nothing

Targets:

    slides.txt          78-column ASCII deck, form-feed separated
    slides.html         self-contained deck: keyboard nav, timer, notes
    slides.pptx         16:9 deck with the script in the speaker notes
    speaker_script.md   timed script with cut list and question prep

Validation runs before anything is written: body lines must fit the ASCII
frame, spoken word counts must sit within `WORD_TOLERANCE` of each slide's
time budget, and slide windows must be contiguous.
"""

from __future__ import annotations

import argparse
import html
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deck import (  # noqa: E402
    ASCII_SKIP,
    QUESTIONS,
    RICH_SKIP,
    RUNNING_LONG,
    RUNNING_SHORT,
    SLIDES,
    TEXT_WIDTH,
    TOTAL_SECONDS,
    WORD_TOLERANCE,
    WORDS_PER_MINUTE,
    Block,
    Bullets,
    Para,
    Pre,
    Slide,
)

HERE = Path(__file__).resolve().parent
FRAME_INNER = TEXT_WIDTH + 4          # columns between the border pipes
FRAME_WIDTH = FRAME_INNER + 2


# --------------------------------------------------------------------------
# Shared body layout, consumed by the ASCII and PPTX renderers
# --------------------------------------------------------------------------

def ascii_blocks(slide: Slide) -> list[Block]:
    """The blocks the terminal deck shows."""
    return [b for b in slide.blocks if b.role not in ASCII_SKIP]


def rich_blocks(slide: Slide) -> list[Block]:
    """The blocks the HTML and PPTX decks show."""
    return [b for b in slide.blocks if b.role not in RICH_SKIP]


def body_lines(slide: Slide, blocks: list[Block] | None = None) -> list[str]:
    """Flatten a slide's blocks into plain monospace lines."""
    out: list[str] = []
    for index, block in enumerate(ascii_blocks(slide) if blocks is None else blocks):
        if index:
            out.append("")
        if isinstance(block, Pre):
            out.extend(block.lines)
        elif isinstance(block, Para):
            out.extend(textwrap.wrap(block.text, width=TEXT_WIDTH) or [""])
        elif isinstance(block, Bullets):
            for item in block.items:
                wrapped = textwrap.wrap(
                    item,
                    width=TEXT_WIDTH,
                    initial_indent="  . ",
                    subsequent_indent="    ",
                )
                out.extend(wrapped)
        else:
            raise TypeError(f"unknown block type: {type(block)!r}")
    return out


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate() -> list[str]:
    problems: list[str] = []

    if TOTAL_SECONDS != 480:
        problems.append(f"deck runs {TOTAL_SECONDS}s, expected 480s (8 min)")

    previous_end = 0
    for number, slide in enumerate(SLIDES, start=1):
        if slide.start != previous_end:
            problems.append(
                f"slide {number:02d}: starts at {slide.start}s but the previous "
                f"slide ends at {previous_end}s"
            )
        previous_end = slide.end

        for line in body_lines(slide):
            if len(line) > TEXT_WIDTH:
                problems.append(
                    f"slide {number:02d}: body line is {len(line)} columns, "
                    f"max is {TEXT_WIDTH}: {line!r}"
                )

        drift = slide.spoken_words - slide.word_budget
        if abs(drift) > WORD_TOLERANCE:
            problems.append(
                f"slide {number:02d}: script is {slide.spoken_words} words but the "
                f"{slide.seconds}s window budgets {slide.word_budget} "
                f"(drift {drift:+d}, tolerance +/-{WORD_TOLERANCE})"
            )

    return problems


def report_budget() -> None:
    total = sum(s.spoken_words for s in SLIDES)
    print(f"{'#':>3}  {'window':<15} {'secs':>5} {'words':>6} {'budget':>7} {'drift':>6}")
    for number, slide in enumerate(SLIDES, start=1):
        print(
            f"{number:>3}  {slide.window:<15} {slide.seconds:>5} "
            f"{slide.spoken_words:>6} {slide.word_budget:>7} "
            f"{slide.spoken_words - slide.word_budget:>+6}"
        )
    print(
        f"\ntotal {total} spoken words -> {total / WORDS_PER_MINUTE:.2f} min at "
        f"{WORDS_PER_MINUTE} wpm, over a {TOTAL_SECONDS / 60:.0f} min slot"
    )


# --------------------------------------------------------------------------
# ASCII
# --------------------------------------------------------------------------

def render_ascii() -> str:
    pages = []
    for number, slide in enumerate(SLIDES, start=1):
        heavy = "+" + "=" * FRAME_INNER + "+"
        thin = "+" + "-" * FRAME_INNER + "+"
        left = f"{number:02d} / {len(SLIDES)}"
        pad = TEXT_WIDTH - len(left) - len(slide.window)
        rows = [
            heavy,
            f"|  {left}{' ' * pad}{slide.window}  |",
            f"|  {slide.title.ljust(TEXT_WIDTH)}  |",
            thin,
            f"|  {' ' * TEXT_WIDTH}  |",
        ]
        for line in body_lines(slide):
            rows.append(f"|  {line.ljust(TEXT_WIDTH)}  |")
        rows.append(f"|  {' ' * TEXT_WIDTH}  |")
        rows.append(heavy)
        pages.append("\n".join(rows) + "\n")
    return "\f\n".join(pages)


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

HTML_CSS = """
/* Palette, type and metrics lifted from the CBSoft'26 talk template:
   #efeee7 paper, #2b2c30 ink, Playfair Display over Public Sans, a hairline
   under a tracked-out kicker, and the slide number alone in the corner. */
:root {
  --bg: #efeee7;
  --ink: #2b2c30;
  --dim: rgba(43, 44, 48, 0.55);
  --rule: rgba(43, 44, 48, 0.32);
  --hair: rgba(43, 44, 48, 0.16);
  --panel: rgba(43, 44, 48, 0.045);
  --paper: #f6f5f0;
  --warn: #9a6a10;
  --late: #a3352b;
  --serif: "Playfair Display", "Playfair Display Variable", "Iowan Old Style",
           Georgia, "Liberation Serif", "Times New Roman", serif;
  --sans: "Public Sans", "Helvetica Neue", Helvetica, Arial, system-ui,
          sans-serif;
  --mono: ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas,
          "DejaVu Sans Mono", "Liberation Mono", monospace;
  /* 81/1440 of the template's slide width. */
  --margin: 5.6vw;
}
* { box-sizing: border-box; }
html, body {
  margin: 0; height: 100%; background: var(--bg); color: var(--ink);
  font-family: var(--serif); overflow: hidden;
  -webkit-font-smoothing: antialiased;
}
#deck { height: 100%; }
.slide {
  display: none; height: 100%;
  padding: 5vh var(--margin) 11vh; flex-direction: column;
  font-size: 2vh;   /* replaced per slide by the auto-fitter in JS */
}
.slide.active { display: flex; }
/* Laid out but invisible, so the fitter can measure an inactive slide. */
.slide.measuring {
  display: flex; visibility: hidden;
  position: absolute; inset: 0; pointer-events: none;
}

/* Kicker plus hairline, as on every content slide of the template. */
.slide-head { flex: none; margin-bottom: 1.3em; }
.slide-title {
  font-family: var(--sans); font-size: 1.15em; font-weight: 700;
  letter-spacing: 0.2em; text-transform: uppercase; line-height: 1.25;
  padding-bottom: 0.55em; border-bottom: 0.75px solid var(--rule);
}
.slide-body { flex: 1 1 auto; min-height: 0; }
.slide-body > * { margin: 0 0 1.1em; }
.slide-body > *:last-child { margin-bottom: 0; }

/* Diagrams and tables stay monospace so their columns keep lining up. */
pre {
  font-family: var(--mono); font-size: 0.94em; line-height: 1.3;
  margin: 0 0 1.1em; padding: 0.75em 1em; white-space: pre; overflow: visible;
  background: var(--panel); border: 0.75px solid var(--hair);
  /* Hug the art rather than stretch, like the boxed figures in the template. */
  width: fit-content; max-width: 100%;
}
p { line-height: 1.4; max-width: 46em; }
ul { margin: 0 0 1.1em; padding-left: 1.5em; list-style: none; }
li { line-height: 1.4; margin-bottom: 0.4em; max-width: 44em; position: relative; }
/* The template marks list items with a small filled square. */
li::before {
  content: ""; position: absolute; left: -1.1em; top: 0.5em;
  width: 0.3em; height: 0.3em; background: var(--ink);
}
strong { font-weight: 700; }

/* Roles set on blocks in deck.py */
/* Display type is sized off the viewport, not the slide's auto-fit scale, so
   it keeps the template's proportions. Wraps after the comma at 20ch. */
p.title {
  font-size: min(8.4vw, 14.6vh); line-height: 1.04; max-width: 20ch;
  letter-spacing: -0.005em; margin-bottom: 0.45em;
}
p.kicker {
  font-family: var(--sans); font-size: 1.15em; font-weight: 700;
  letter-spacing: 0.2em; text-transform: uppercase; line-height: 1.35;
  max-width: none; padding-top: 0.7em; border-top: 0.75px solid var(--rule);
}
p.credit {
  font-family: var(--sans); font-size: 0.82em; font-weight: 400;
  line-height: 1.5; color: var(--dim); max-width: none; margin-bottom: 0.3em;
}
p.punch { font-size: 1.5em; font-style: italic; line-height: 1.2; }

/* Title slide: display type flush left, credits pinned to the foot. */
.slide.title { justify-content: flex-start; padding-top: 8vh; font-size: 2.6vh; }
.slide.title .slide-head { display: none; }
.slide.title .slide-body { display: flex; flex-direction: column; }
.slide.title p.kicker { margin-bottom: auto; }
.slide.title p.credit:first-of-type { margin-top: 1.4em; }

/* Slide number, bottom right, Playfair, nothing else around it. */
#page-num {
  position: fixed; right: var(--margin); bottom: 3.4vh;
  font-family: var(--serif); font-size: 3.4vh; line-height: 1;
}
#page-num.hidden { visibility: hidden; }

/* Presenter strip: deliberately quiet, toggled off with h. */
#hud {
  position: fixed; left: var(--margin); right: 22vw; bottom: 3.6vh;
  display: flex; align-items: baseline; gap: 1.6em;
  font-family: var(--sans); font-size: 0.72rem; letter-spacing: 0.02em;
  color: var(--dim);
}
#hud.hidden { display: none; }
#hud b { color: var(--ink); font-weight: 600; }
#clock.behind { color: var(--warn); }
#clock.late { color: var(--late); }
#bar {
  position: fixed; left: 0; bottom: 0; height: 2px;
  background: var(--ink); opacity: 0.4; transition: width 0.18s ease;
}

/* Speaker notes */
#notes {
  position: fixed; right: 0; top: 0; bottom: 0; width: min(34rem, 42vw);
  padding: 1.6em 1.8em; overflow-y: auto;
  font-family: var(--sans); font-size: 0.82rem; line-height: 1.6;
  background: var(--paper); border-left: 0.75px solid var(--rule);
  transform: translateX(101%); transition: transform 0.2s ease;
}
#notes.open { transform: translateX(0); }
#notes h3 {
  margin: 0 0 1em; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.2em;
  text-transform: uppercase; padding-bottom: 0.6em;
  border-bottom: 0.75px solid var(--rule);
}
#notes p { max-width: none; margin: 0 0 0.9em; line-height: 1.6; }
#notes .cue {
  color: var(--warn); border-left: 2px solid var(--warn);
  padding-left: 0.8em; margin-bottom: 0.9em;
}
#notes .opt {
  color: var(--dim); border-left: 2px solid var(--hair);
  padding-left: 0.8em;
}

@media print {
  html, body { overflow: visible; height: auto; }
  #hud, #notes, #bar { display: none; }
  .slide {
    display: flex !important; height: 100vh; page-break-after: always;
    /* Beats the auto-fitter's inline size, which is sized for the screen. */
    font-size: 11pt !important;
  }
  .slide.measuring { position: static; visibility: visible; }
}
"""

HTML_JS = """
const slides = Array.from(document.querySelectorAll('.slide'));
const notes = document.getElementById('notes');
const bar = document.getElementById('bar');
const hud = document.getElementById('hud');
const counter = document.getElementById('counter');
const target = document.getElementById('target');
const clock = document.getElementById('clock');
const pageNum = document.getElementById('page-num');
const TOTAL = Number(document.body.dataset.total);
let index = 0;
let started = null;

/* Binary-search the largest font size at which a slide's body neither
   overflows its box nor pushes the 72-column monospace art past the margin.
   Doing it here rather than with a CSS heuristic means every slide fills the
   projector, whatever its aspect ratio. */
function fit(slide) {
  if (slide.classList.contains('title')) return;
  const body = slide.querySelector('.slide-body');
  const offstage = !slide.classList.contains('active');
  if (offstage) slide.classList.add('measuring');
  let lo = 6, hi = 34;
  for (let step = 0; step < 16; step++) {
    const mid = (lo + hi) / 2;
    slide.style.fontSize = mid + 'px';
    const fits = body.scrollHeight <= body.clientHeight + 1 &&
                 body.scrollWidth <= body.clientWidth + 1;
    if (fits) lo = mid; else hi = mid;
  }
  slide.style.fontSize = lo.toFixed(2) + 'px';
  if (offstage) slide.classList.remove('measuring');
}

function fitAll() { slides.forEach(fit); }

function show(next) {
  index = Math.max(0, Math.min(slides.length - 1, next));
  slides.forEach((s, i) => s.classList.toggle('active', i === index));
  const slide = slides[index];
  counter.textContent = `${String(index + 1).padStart(2, '0')} / ${slides.length}`;
  target.textContent = slide.dataset.window;
  bar.style.width = `${((index + 1) / slides.length) * 100}%`;
  // The template leaves the title slide unnumbered.
  pageNum.textContent = index;
  pageNum.classList.toggle('hidden', slide.classList.contains('title'));
  notes.innerHTML = slide.querySelector('template').innerHTML;
  location.hash = index + 1;
}

function tick() {
  if (started === null) { clock.textContent = '--:-- idle'; return; }
  const elapsed = Math.floor((Date.now() - started) / 1000);
  const mm = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const ss = String(elapsed % 60).padStart(2, '0');
  clock.textContent = `${mm}:${ss}`;
  // Compare against where this slide should have ended.
  const due = Number(slides[index].dataset.end);
  clock.className = elapsed > TOTAL ? 'late' : (elapsed > due ? 'behind' : '');
}

document.addEventListener('keydown', (event) => {
  const key = event.key;
  if (['ArrowRight', 'ArrowDown', 'PageDown', ' ', 'Enter'].includes(key)) {
    if (started === null) started = Date.now();
    show(index + 1); event.preventDefault();
  } else if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(key)) {
    show(index - 1); event.preventDefault();
  } else if (key === 'Home') { show(0); }
  else if (key === 'End') { show(slides.length - 1); }
  else if (key === 's' || key === 'S') { notes.classList.toggle('open'); }
  else if (key === 'h' || key === 'H') { hud.classList.toggle('hidden'); }
  else if (key === 'f' || key === 'F') {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen();
  } else if (key === 't' || key === 'T') {
    started = started === null ? Date.now() : null;
  } else if (key === 'r' || key === 'R') { started = Date.now(); }
});

document.addEventListener('click', (event) => {
  if (event.target.closest('#notes') || event.target.closest('#hud')) return;
  if (started === null) started = Date.now();
  show(index + 1);
});

show(Number(location.hash.slice(1)) - 1 || 0);
fitAll();
addEventListener('resize', fitAll);
if (document.fonts) document.fonts.ready.then(fitAll);
setInterval(tick, 250);
tick();
"""


def _html_blocks(slide: Slide) -> str:
    parts = []
    for block in rich_blocks(slide):
        cls = f' class="{block.role}"' if block.role else ""
        if isinstance(block, Pre):
            parts.append(f"<pre{cls}>" + html.escape("\n".join(block.lines)) + "</pre>")
        elif isinstance(block, Para):
            parts.append(f"<p{cls}>" + html.escape(block.text) + "</p>")
        elif isinstance(block, Bullets):
            items = "".join(f"<li>{html.escape(i)}</li>" for i in block.items)
            parts.append(f"<ul{cls}>{items}</ul>")
    return "\n".join(parts)


def _html_notes(slide: Slide, number: int) -> str:
    parts = [f"<h3>Slide {number:02d} &middot; {html.escape(slide.window)}</h3>"]
    if slide.delivery:
        parts.append(f'<p class="cue">{html.escape(slide.delivery)}</p>')
    parts.extend(f"<p>{html.escape(p)}</p>" for p in slide.script)
    if slide.optional:
        parts.append(
            f'<p class="opt">Only if ahead of the clock: '
            f'&ldquo;{html.escape(slide.optional)}&rdquo;</p>'
        )
    parts.append(
        f"<p class=\"opt\">{slide.spoken_words} words for a {slide.seconds}s "
        f"window (budget {slide.word_budget}).</p>"
    )
    return "\n".join(parts)


def render_html() -> str:
    sections = []
    for number, slide in enumerate(SLIDES, start=1):
        classes = "slide title" if slide.kind == "title" else "slide"
        sections.append(
            f'<section class="{classes}"'
            f' data-window="{html.escape(slide.window)}" data-end="{slide.end}">\n'
            f'  <div class="slide-head">\n'
            f'    <div class="slide-title">{html.escape(slide.title)}</div>\n'
            f'  </div>\n'
            f'  <div class="slide-body">\n{_html_blocks(slide)}\n  </div>\n'
            f'  <template>{_html_notes(slide, number)}</template>\n'
            f'</section>'
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Grading Is Easy, Feedback Is Hard &mdash; Artifacts Festival</title>
<style>{HTML_CSS}</style>
</head>
<body data-total="{TOTAL_SECONDS}">
<div id="deck">
{chr(10).join(sections)}
</div>
<div id="bar"></div>
<div id="page-num"></div>
<div id="hud">
  <span><b id="counter">01 / {len(SLIDES)}</b> &nbsp; target <b id="target"></b></span>
  <span>elapsed <b id="clock">--:--</b> / {_mmss(TOTAL_SECONDS)}</span>
  <span><b>s</b> notes &middot; <b>t</b> timer &middot; <b>h</b> hide</span>
</div>
<aside id="notes"></aside>
<script>{HTML_JS}</script>
</body>
</html>
"""


def _mmss(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# --------------------------------------------------------------------------
# PPTX
# --------------------------------------------------------------------------

# Same palette as the HTML deck, read off the CBSoft'26 template.
BG = 0xEFEEE7
INK = 0x2B2C30
DIM = 0x82838A
HAIR = 0xD5D3CB
SERIF = "Playfair Display"
SANS = "Public Sans"
MONO = "Courier New"        # chosen for availability: ASCII tables must not reflow

MARGIN_IN = 0.75            # 81/1440 of the template's slide width
CONTENT_W_IN = 11.83        # 1278/1440
NATURAL_LEADING = 1.21      # Courier New's own line height, in ems


def _split_display(text: str) -> list[str]:
    """Split a display line at its commas, keeping them on the leading part."""
    parts = [p.strip() for p in text.split(",") if p.strip()]
    return [p + "," for p in parts[:-1]] + parts[-1:] if len(parts) > 1 else [text]


def render_pptx(path: Path) -> None:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_CONNECTOR
    from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
    from pptx.util import Inches, Pt

    def rgb(value: int) -> RGBColor:
        return RGBColor((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)

    def track_out(run, hundredths: int) -> None:
        """Letter-space a run; python-pptx has no API for it, so set the XML."""
        run.font._rPr.set("spc", str(hundredths))

    def textbox(slide, left, top, width, height, *, wrap=True):
        frame = slide.shapes.add_textbox(left, top, width, height).text_frame
        frame.word_wrap = wrap
        # Without this, a no-wrap box grows to fit and some renderers then
        # re-centre it, pulling the ASCII art off the left margin.
        frame.auto_size = MSO_AUTO_SIZE.NONE
        frame.margin_left = frame.margin_right = 0
        frame.margin_top = frame.margin_bottom = 0
        return frame

    def write(para, text, *, font, size, bold=False, italic=False, color=INK,
              spacing=None):
        run = para.add_run()
        run.text = text
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = rgb(color)
        if spacing:
            track_out(run, spacing)
        return run

    deck = Presentation()
    deck.slide_width = Inches(13.333)
    deck.slide_height = Inches(7.5)
    blank = deck.slide_layouts[6]

    left = Inches(MARGIN_IN)
    content_w = Inches(CONTENT_W_IN)
    body_top, body_h = Inches(1.42), Inches(5.2)
    line_spacing = 1.18

    for number, slide_spec in enumerate(SLIDES, start=1):
        slide = deck.slides.add_slide(blank)

        background = slide.background
        background.fill.solid()
        background.fill.fore_color.rgb = rgb(BG)

        is_title = slide_spec.kind == "title"
        blocks = rich_blocks(slide_spec)

        if is_title:
            head = textbox(slide, left, Inches(0.72), content_w, Inches(2.4))
            # Break after the comma, as the template does, instead of wherever
            # the box happens to run out.
            title_lines = [
                part
                for block in blocks
                if isinstance(block, Para) and block.role == "title"
                for part in _split_display(block.text)
            ]
            for position, line in enumerate(title_lines):
                para = head.paragraphs[0] if position == 0 else head.add_paragraph()
                para.line_spacing = 1.02
                write(para, line, font=SERIF, size=66)

            rule = slide.shapes.add_connector(
                MSO_CONNECTOR.STRAIGHT, left, Inches(3.28),
                left + content_w, Inches(3.28),
            )
            rule.line.color.rgb = rgb(INK)
            rule.line.width = Pt(0.75)

            kicker = textbox(slide, left, Inches(3.48), content_w, Inches(0.9))
            for position, block in enumerate(
                b for b in blocks if isinstance(b, Para) and b.role == "kicker"
            ):
                para = kicker.paragraphs[0] if position == 0 else kicker.add_paragraph()
                para.line_spacing = 1.35
                write(para, block.text.upper(), font=SANS, size=17, bold=True,
                      spacing=340)

            credits = textbox(slide, left, Inches(5.35), content_w, Inches(1.6))
            for position, block in enumerate(
                b for b in blocks if isinstance(b, Para) and b.role == "credit"
            ):
                para = (credits.paragraphs[0] if position == 0
                        else credits.add_paragraph())
                para.line_spacing = 1.5
                write(para, block.text, font=SANS, size=11, color=DIM)

            _pptx_notes(slide, slide_spec, number)
            continue

        head = textbox(slide, left, Inches(0.52), content_w, Inches(0.62))
        head.vertical_anchor = MSO_ANCHOR.BOTTOM
        write(head.paragraphs[0], slide_spec.title.upper(), font=SANS, size=17,
              bold=True, spacing=340)

        rule = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, left, Inches(1.24), left + content_w, Inches(1.24),
        )
        rule.line.color.rgb = rgb(HAIR)
        rule.line.width = Pt(0.75)

        lines = body_lines(slide_spec, blocks)

        # Auto-fit: Courier New advances 0.6em per character, and a spacing
        # multiple of 1.0 already leaves ~1.17em between baselines.
        widest = max((len(l) for l in lines), default=1) or 1
        by_width = (CONTENT_W_IN * 72) / (widest * 0.60)
        by_height = (body_h.inches * 72) / (
            max(len(lines), 1) * line_spacing * NATURAL_LEADING
        )
        size = max(9.0, min(by_width, by_height, 16.0))

        frame = textbox(slide, left, body_top, content_w, body_h, wrap=False)
        for position, line in enumerate(lines):
            para = frame.paragraphs[0] if position == 0 else frame.add_paragraph()
            para.line_spacing = line_spacing
            para.alignment = PP_ALIGN.LEFT
            write(para, line, font=MONO, size=size)

        # The template leaves the title slide unnumbered and counts from there.
        corner = textbox(slide, left, Inches(6.82), content_w, Inches(0.45))
        corner.paragraphs[0].alignment = PP_ALIGN.RIGHT
        write(corner.paragraphs[0], str(number - 1), font=SERIF, size=20)

        _pptx_notes(slide, slide_spec, number)

    deck.save(path)


def _pptx_notes(slide, slide_spec: Slide, number: int) -> None:
    chunks = [f"[{slide_spec.window}]  slide {number:02d} of {len(SLIDES)}"]
    if slide_spec.delivery:
        chunks.append(f"CUE: {slide_spec.delivery}")
    chunks.extend(slide_spec.script)
    if slide_spec.optional:
        chunks.append(f"IF AHEAD: {slide_spec.optional}")
    chunks.append(
        f"({slide_spec.spoken_words} words / {slide_spec.seconds}s window, "
        f"budget {slide_spec.word_budget})"
    )
    slide.notes_slide.notes_text_frame.text = "\n\n".join(chunks)


# --------------------------------------------------------------------------
# Speaker script
# --------------------------------------------------------------------------

def render_script() -> str:
    total = sum(s.spoken_words for s in SLIDES)
    out = [
        "# Artifacts Festival — 8-minute speaker script",
        "",
        "<!-- Generated by render.py from deck.py. Edit deck.py, not this file. -->",
        "",
        "Companion to [`slides.txt`](slides.txt), [`slides.html`](slides.html) and",
        "[`slides.pptx`](slides.pptx) — the PPTX carries this script in its speaker",
        f"notes. Target pace is {WORDS_PER_MINUTE} words per minute; the spoken text is",
        f"{total} words over a {TOTAL_SECONDS // 60}-minute slot.",
        "",
        "| Slide | Window | Section | Words |",
        "| ---: | :--- | :--- | ---: |",
    ]
    for number, slide in enumerate(SLIDES, start=1):
        out.append(
            f"| {number:02d} | {slide.window} | {slide.title.title()} "
            f"| {slide.spoken_words} |"
        )
    out.append("")

    for number, slide in enumerate(SLIDES, start=1):
        out += ["---", "", f"## Slide {number:02d} — {slide.title.title()} · {slide.window}", ""]
        if slide.delivery:
            out += [f"> Delivery: {slide.delivery}", ""]
        for paragraph in slide.script:
            out += textwrap.wrap(paragraph, width=79) + [""]
        if slide.optional:
            out += textwrap.wrap(
                f'> Optional, only if ahead of the clock: "{slide.optional}"',
                width=79,
                subsequent_indent="> ",
            ) + [""]

    out += ["---", "", "## If you are running long", "",
            "Cut in this order. Each cut is self-contained and costs no continuity.", ""]
    for position, item in enumerate(RUNNING_LONG, start=1):
        out += textwrap.wrap(
            f"{position}. {item}", width=79, subsequent_indent="   "
        )
    out += [
        "",
        "Do not cut slides 05, 06 or 10. The prompt structure, the injection "
        "mechanism and the one-command reproduction are what the audience came for.",
        "",
        "## If you are running short",
        "",
    ]
    for item in RUNNING_SHORT:
        out += textwrap.wrap(item, width=79) + [""]

    out += ["## Question prep", ""]
    for question, answer in QUESTIONS:
        out += [f"**{question}**"]
        out += textwrap.wrap(answer, width=79) + [""]

    return "\n".join(out).rstrip("\n") + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ascii", action="store_true", help="write slides.txt")
    parser.add_argument("--html", action="store_true", help="write slides.html")
    parser.add_argument("--pptx", action="store_true", help="write slides.pptx")
    parser.add_argument("--script", action="store_true", help="write speaker_script.md")
    parser.add_argument("--check", action="store_true", help="validate only")
    parser.add_argument("--budget", action="store_true", help="print the word budget")
    args = parser.parse_args()

    problems = validate()
    if problems:
        print("deck validation failed:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    if args.budget:
        report_budget()
    if args.check:
        print(f"deck ok: {len(SLIDES)} slides, {TOTAL_SECONDS}s")
        return 0

    selected = args.ascii or args.html or args.pptx or args.script
    written = []

    if args.ascii or not selected:
        path = HERE / "slides.txt"
        path.write_text(render_ascii(), encoding="ascii")
        written.append(path)
    if args.html or not selected:
        path = HERE / "slides.html"
        path.write_text(render_html(), encoding="utf-8")
        written.append(path)
    if args.pptx or not selected:
        path = HERE / "slides.pptx"
        try:
            render_pptx(path)
        except ImportError:
            print(
                "python-pptx is not installed; skipping slides.pptx\n"
                "  python3 -m pip install -r docs/presentation/requirements.txt",
                file=sys.stderr,
            )
        else:
            written.append(path)
    if args.script or not selected:
        path = HERE / "speaker_script.md"
        path.write_text(render_script(), encoding="utf-8")
        written.append(path)

    for path in written:
        print(f"wrote {path.relative_to(HERE.parents[1])} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
