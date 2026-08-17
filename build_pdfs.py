#!/usr/bin/env python3
"""
Build the printable We Out Here 2026 PDFs from data.json.

Two files, both A4 landscape, matching the on-site design but styled for
printing on a home printer:

  we-out-here-2026-set-times.pdf         8 pages - 4 days x 2 sides
                                         side 1: the 6 main stages
                                         side 2: the other 11 areas
  we-out-here-2026-wider-programme.pdf   1 page per day - talks, workshops,
                                         wellbeing

Print styling: event boxes are white with a coloured left rule rather than a
shaded fill, so they stay crisp in greyscale and use a fraction of the ink.
Hour lines are solid, half hours dotted, and every page carries the time
gutter down both edges.

data.json is the single source of truth - run check-updates.py first, apply any
changes, then re-run this.

Usage:
    python3 build_pdfs.py
    python3 build_pdfs.py --stamp "17 Aug, 7pm"
"""

import argparse
import asyncio
import json
import os
import re
from collections import defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(HERE, "data.json")
SET_TIMES_PDF = os.path.join(HERE, "we-out-here-2026-set-times.pdf")
WIDER_PDF = os.path.join(HERE, "we-out-here-2026-wider-programme.pdf")

# Must stay in step with STAGES in index.html.
STAGES = [
    "Main Stage", "Lush Life", "Rhythm Corner", "The Grove", "The Bowl",
    "Tomorrow's Warriors Big Top", "Roller Rink", "Love Dancin'",
    "Lemon Lounge", "Brawnswood", "Worldwide FM: WOH Radio", "Carhartt WIP",
    "Beat Hotel x Ilegal Mezcal", "Passenger: Ground Tempo",
    "Near Mint Record Store", "Love-Serve Bar", "Once In A Blue Moon",
    "Talks Tent", "The Knowledge", "BookLove", "Craftwerk",
    "Craftwerk: Outdoors", "Lemon Lounge Workshops", "The Sanctuary",
    "Wellbeing Tent", "Wellness Tent: The Clearing",
    "Near Mint Record Signings", "Action Station",
]

# Column headings are tight, so a few stages get a shorter label.
SHORT = {
    5: "Tomorrow's Warriors", 10: "WOH Radio", 12: "Beat Hotel",
    13: "Ground Tempo", 14: "Near Mint Records", 21: "Craftwerk Out.",
    22: "Lemon Lounge Wkshp", 25: "The Clearing", 26: "Near Mint Signings",
}

# Deeper than the app's screen palette - these have to hold up as a thin rule
# on paper, and stay distinguishable when printed in greyscale.
COLOURS = [
    "#7a2e4e", "#1c7268", "#c0662a", "#4a57a8", "#78871f", "#b22a5c",
    "#8e2f55", "#1b7a70", "#c8791f", "#43509e", "#6f7f1b", "#c0392b",
    "#2e7d4f", "#a0763c", "#3f51a0", "#b5316e", "#17726a",
    "#7a2e4e", "#1c7268", "#c0662a", "#4a57a8", "#6f7f1b", "#b22a5c",
    "#2e7d4f", "#a0763c", "#5b4fa8", "#8e5a2f", "#b5316e",
]

MAIN_STAGES = list(range(0, 6))       # side 1
OTHER_AREAS = list(range(6, 17))      # side 2
WIDER = list(range(17, 28))           # separate document

# A4 landscape at 96dpi is 1123 x 794. Leave room for the header, the column
# headings and the footer; whatever is left is the grid.
BODY_PX = 618
MIN_BOX_PX = 15


def hhmm(t):
    """900 -> '3pm', 1470 -> '12:30am'."""
    t = ((t % 1440) + 1440) % 1440
    h, m = divmod(t, 60)
    suffix = "am" if h < 12 else "pm"
    hour = h % 12 or 12
    return f"{hour}:{m:02d}{suffix}" if m else f"{hour}{suffix}"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def day_title(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    dt = date(y, m, d)
    return dt.strftime("%A") + " " + str(d) + " " + dt.strftime("%B")


def assign_lanes(events):
    """Split a column into side-by-side lanes if anything overlaps.

    Nothing overlaps in the current data, but the festival has form for adding
    a set on top of another one, and silently stacking two boxes in the same
    space would be worse than a narrow column.
    """
    events = sorted(events, key=lambda e: (e[0], e[1]))
    lane_ends = []
    placed = []
    for ev in events:
        for i, end in enumerate(lane_ends):
            if ev[0] >= end:
                lane_ends[i] = ev[1]
                placed.append((ev, i))
                break
        else:
            lane_ends.append(ev[1])
            placed.append((ev, len(lane_ends) - 1))
    return placed, max(1, len(lane_ends))


def page_html(title, side_label, sub_label, events, stage_ids, stamp,
              footer_note, kicker_suffix=""):
    """One grid page."""
    by_stage = defaultdict(list)
    for ev in events:
        by_stage[ev[2]].append(ev)
    # Drop areas with nothing on that day - empty columns just waste width.
    cols = [s for s in stage_ids if by_stage.get(s)]
    if not cols:
        return ""

    lo = min(e[0] for e in events) // 60 * 60
    hi = -(-max(e[1] for e in events) // 60) * 60
    hours = max(1, (hi - lo) // 60)
    px_per_min = BODY_PX / (hours * 60)

    gutter = "".join(
        f'<div class="hr" style="top:{(h * 60) * px_per_min:.2f}px">'
        f'<span>{hhmm(lo + h * 60)}</span></div>'
        for h in range(hours + 1))

    lines = "".join(
        f'<div class="{"hl" if (lo + m) % 60 == 0 else "hl half"}" '
        f'style="top:{m * px_per_min:.2f}px"></div>'
        for m in range(0, hours * 60 + 1, 30))

    # 11 columns share the same width as 6, so the headings have to come down
    # a couple of points or the longer area names clip.
    n_cols = len(cols)
    hdr = ("font-size:7.6px;letter-spacing:0.75px" if n_cols <= 6
           else "font-size:7.1px;letter-spacing:0.45px" if n_cols <= 8
           else "font-size:6.5px;letter-spacing:0.2px")

    col_html = []
    for s in cols:
        placed, lanes = assign_lanes(by_stage[s])
        # How far each box may grow before it would hit the next one in its
        # lane. A 30-minute talk with a long title is unreadable squeezed into
        # its slot, but there is nearly always empty grid underneath it.
        next_start = {}
        for i, (ev, lane) in enumerate(placed):
            limit = hi
            for other, ol in placed[i + 1:]:
                if ol == lane:
                    limit = other[0]
                    break
            next_start[id(ev)] = limit

        boxes = []
        for ev, lane in placed:
            start, end, _stage, name = ev
            top = (start - lo) * px_per_min
            slot = max(MIN_BOX_PX, (end - start) * px_per_min - 1.5)
            room = max(slot, (next_start[id(ev)] - start) * px_per_min - 1.5)
            width = 100.0 / lanes
            left = width * lane
            # Long names get a smaller face; the box itself may also grow down
            # into free grid, so nothing has to be cut off.
            n = len(name)
            size = ("6.6" if n > 104 else "7.1" if n > 78
                    else "7.7" if n > 52 else "8.4")
            flag = ""
            if name.strip().lower() == "melomaniacs":
                flag = '<div class="unmiss">&#9733; UNMISSABLE</div>'
            boxes.append(
                f'<div class="ev" data-top="{top:.2f}" data-slot="{slot:.2f}" '
                f'data-lane="{lane}" style="top:{top:.2f}px;'
                f'min-height:{slot:.2f}px;'
                f'left:{left:.4f}%;width:calc({width:.4f}% - 2px);'
                f'border-left-color:{COLOURS[s]}">'
                f'<div class="t" style="color:{COLOURS[s]}">'
                f'{esc(hhmm(start))}&#8211;{esc(hhmm(end))}</div>'
                f'<div class="n" style="font-size:{size}px">{esc(name)}</div>'
                f'{flag}</div>')
        col_html.append(
            f'<div class="col">'
            f'<div class="ch" style="background:{COLOURS[s]};{hdr}">'
            f'{esc(SHORT.get(s, STAGES[s]).upper())}</div>'
            f'<div class="track" style="height:{BODY_PX}px">'
            f'{lines}{"".join(boxes)}</div></div>')

    return f"""
<section class="page">
  <header>
    <div>
      <div class="kicker">WE OUT HERE <b>2026</b>{kicker_suffix}</div>
      <h1>{esc(title)}</h1>
    </div>
    <div class="side">
      <div class="sl">{esc(side_label)}</div>
      <div class="sn">{esc(sub_label.strip(' ·') or '')}</div>
    </div>
  </header>
  <div class="grid">
    <div class="gut">
      <div class="ch blank"></div>
      <div class="track" style="height:{BODY_PX}px">{gutter}</div>
    </div>
    {''.join(col_html)}
    <div class="gut right">
      <div class="ch blank"></div>
      <div class="track" style="height:{BODY_PX}px">{gutter}</div>
    </div>
  </div>
  <footer>
    <div>{esc(footer_note)} &#183; times correct as of <b>{esc(stamp)}</b></div>
    <div class="brand">MADE BY <b>BITASUITE</b> FOR THE MELOMANIACS &#183;
      mixcloud.com/MelomaniacsCollective</div>
  </footer>
</section>"""


CSS = """
@page { size: A4 landscape; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: "Helvetica Neue", Helvetica, Arial, "DejaVu Sans", sans-serif;
  color: #111; -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
.page {
  width: 1123px; height: 794px; padding: 26px 30px 16px;
  display: flex; flex-direction: column; page-break-after: always;
  position: relative; background: #fff;
}
.page:last-child { page-break-after: auto; }
header { display: flex; justify-content: space-between; align-items: flex-start; }
.kicker { font-size: 11px; letter-spacing: 2.2px; font-weight: 700; color: #444; }
.kicker b { color: #b22a5c; }
h1 { margin: 2px 0 0; font-size: 27px; letter-spacing: -0.4px; }
.side { text-align: right; }
.sl { font-size: 11px; letter-spacing: 2.2px; font-weight: 700; }
.sn { font-size: 8.5px; letter-spacing: 1.4px; color: #666; margin-top: 3px; }
.grid { display: flex; gap: 3px; margin-top: 14px; flex: 1; }
.gut { width: 34px; flex: none; }
.gut .track { position: relative; }
.gut.right { text-align: left; }
.gut .hr { position: absolute; right: 3px; transform: translateY(-50%); }
.gut.right .hr { right: auto; left: 3px; }
.hr span { font-size: 7.5px; color: #555; white-space: nowrap; }
.col { flex: 1 1 0; min-width: 0; }
.ch {
  height: 17px; line-height: 17px; text-align: center; color: #fff;
  font-size: 7.6px; font-weight: 700; letter-spacing: 0.75px;
  overflow: hidden; white-space: nowrap;
}
.ch.blank { background: none; }
.track { position: relative; border-right: 1px solid #d8d8d8; }
.col:first-of-type .track { border-left: 1px solid #d8d8d8; }
.hl { position: absolute; left: 0; right: 0; border-top: 1px solid #c9c9c9; }
.hl.half { border-top: 1px dotted #e6e6e6; }
.ev {
  position: absolute; background: #fff; border: 1px solid #b9b9b9;
  border-left-width: 3.5px; border-left-style: solid;
  padding: 1.5px 4px 1px; overflow: hidden; height: auto;
}
.ev .t { font-size: 6.1px; font-weight: 700; letter-spacing: 0.15px; }
.ev .n { font-weight: 700; line-height: 1.16; margin-top: 0.5px; color: #111; }
.unmiss { font-size: 6px; font-weight: 700; color: #9a7000; letter-spacing: 0.5px; }
footer {
  display: flex; justify-content: space-between; align-items: flex-end;
  margin-top: 8px; font-size: 7px; color: #666;
}
.brand { text-align: right; }
.brand b { color: #111; }
"""


def build_pages(data, stamp):
    set_pages, wider_pages = [], []
    for day in data:
        title = day_title(day["date"])
        ev = day["ev"]
        main = [e for e in ev if e[2] in MAIN_STAGES]
        other = [e for e in ev if e[2] in OTHER_AREAS]
        wide = [e for e in ev if e[2] in WIDER]
        note = ("Set times as published at weoutherefestival.com · "
                "Wimborne St Giles, Dorset · subject to change")
        if main:
            set_pages.append(page_html(title, "MAIN STAGES", " · SIDE 1 OF 2",
                                       main, MAIN_STAGES, stamp, note))
        if other:
            set_pages.append(page_html(title, "THE OTHER AREAS",
                                       " · SIDE 2 OF 2", other, OTHER_AREAS,
                                       stamp, note))
        if wide:
            wider_pages.append(page_html(
                title, "TALKS · WORKSHOPS · WELLBEING",
                f" · {len(wide)} SESSIONS", wide, WIDER, stamp,
                "Wider programme as published at weoutherefestival.com · "
                "some craft sessions need booking · subject to change",
                " · WIDER PROGRAMME"))
    return set_pages, wider_pages


# Box height has to follow the text, not the clock: a 15-minute author signing
# with a 50-character title cannot physically fit its slot, and silently cutting
# the name off makes the printout useless. So after the browser has laid the
# text out (only it knows the real wrapped height) each column is packed in
# time order: a box starts at its true time, or immediately below its
# predecessor if that one had to grow. Dense clusters drift a few minutes low -
# the same compromise the original PDFs made - and the hour rules behind them
# stay exactly where they belong.
PACK_JS = """
<script>
(function () {
  document.querySelectorAll('.col .track').forEach(function (track) {
    var bodyPx = track.offsetHeight;
    var boxes = [].slice.call(track.querySelectorAll('.ev'));
    var lanes = {};
    boxes.forEach(function (b) {
      var lane = b.dataset.lane || '0';
      var want = parseFloat(b.dataset.top);
      var slot = parseFloat(b.dataset.slot);
      var need = Math.max(slot, b.scrollHeight);
      var top = Math.max(want, lanes[lane] == null ? 0 : lanes[lane]);
      b.style.top = top + 'px';
      b.style.height = need + 'px';
      lanes[lane] = top + need + 1.5;
    });
    // If growing pushed a lane past the bottom of the grid, squeeze that
    // lane's gaps back up so it still fits on the page.
    Object.keys(lanes).forEach(function (lane) {
      var over = lanes[lane] - bodyPx;
      if (over <= 0) return;
      var inLane = boxes.filter(function (b) {
        return (b.dataset.lane || '0') === lane;
      });
      var slack = 0;
      for (var i = 1; i < inLane.length; i++) {
        var prev = inLane[i - 1];
        slack += parseFloat(inLane[i].style.top) -
                 (parseFloat(prev.style.top) + parseFloat(prev.style.height));
      }
      var shrink = slack > 0 ? Math.min(1, over / slack) : 0;
      var shift = 0;
      for (var j = 1; j < inLane.length; j++) {
        var p = inLane[j - 1];
        var gap = parseFloat(inLane[j].style.top) -
                  (parseFloat(p.style.top) + parseFloat(p.style.height)) - shift;
        shift += Math.max(0, gap) * shrink;
        inLane[j].style.top = (parseFloat(inLane[j].style.top) - shift) + 'px';
      }
    });
  });
  document.body.dataset.packed = '1';
})();
</script>
"""


def document(pages):
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<style>{CSS}</style></head><body>{''.join(pages)}"
            f"{PACK_JS}</body></html>")


async def render(html, out_path):
    from playwright.async_api import async_playwright
    tmp = out_path + ".html"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("file://" + os.path.abspath(tmp))
        await page.wait_for_function("document.body.dataset.packed === '1'")
        await page.wait_for_timeout(250)
        await page.pdf(path=out_path, format="A4", landscape=True,
                       print_background=True,
                       margin={"top": "0", "right": "0",
                               "bottom": "0", "left": "0"})
        await browser.close()
    os.remove(tmp)


def read_stamp_from_index():
    """Reuse the SCRAPED stamp in index.html so the PDFs can't disagree with
    the app about how fresh the data is."""
    path = os.path.join(HERE, "index.html")
    try:
        with open(path, encoding="utf-8") as f:
            m = re.search(r"var SCRAPED\s*=\s*'([^']*)'", f.read())
        if m:
            return m.group(1)
    except FileNotFoundError:
        pass
    return date.today().strftime("%d %b")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stamp", help="override the 'times correct as of' text")
    args = ap.parse_args()
    stamp = args.stamp or read_stamp_from_index()

    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)

    set_pages, wider_pages = build_pages(data, stamp)
    total = sum(len(d["ev"]) for d in data)
    print(f"{total} events -> {len(set_pages)} set-times pages, "
          f"{len(wider_pages)} wider-programme pages (stamp: {stamp})")

    asyncio.run(render(document(set_pages), SET_TIMES_PDF))
    asyncio.run(render(document(wider_pages), WIDER_PDF))
    for p in (SET_TIMES_PDF, WIDER_PDF):
        print(f"  wrote {os.path.basename(p)} "
              f"({os.path.getsize(p) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
