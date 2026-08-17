#!/usr/bin/env python3
"""
Check the official We Out Here set times against local data.json.

The old version scraped body.innerText, which only ever returned the day tab
that happened to be visible - so three days out of four came back empty and
every artist on them looked "removed".

The site actually puts ALL four days in the DOM at once, inside
  .scheduleCalendarWrap[data-schedule-day="DD/MM/YYYY"]
with one .scheduleCalendar__column[data-stage-id] per stage and one
  .scheduleCalendar__listing
per set. So there is no need to click day tabs at all - we read the DOM
directly, which also gives us the day and the stage for every entry.

There are two schedule pages (music programme and wider programme); both use
the same markup. Both are scraped.

Usage:
    python3 check-updates.py                 # report only
    python3 check-updates.py --json out.json # also dump what was scraped
"""

import argparse
import difflib
import json
import os
import re
import sys
from collections import defaultdict

URLS = [
    ("music", "https://weoutherefestival.com/set-times/"),
    ("wider", "https://weoutherefestival.com/wider-programme-set-times/"),
]

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(HERE, "data.json")

# Site stage id -> index into the STAGES array in index.html.
# If the site adds a stage, the scraper reports it as unmapped rather than
# silently dropping it.
STAGE_ID_TO_INDEX = {
    "40": 0,    # Main Stage
    "42": 1,    # Lush Life
    "43": 2,    # Rhythm Corner
    "77": 3,    # The Grove
    "45": 4,    # The Bowl
    "82": 5,    # Tomorrow's Warriors Big Top
    "83": 6,    # Roller Rink
    "44": 7,    # Love Dancin'
    "84": 8,    # Lemon Lounge
    "78": 9,    # Brawnswood
    "79": 10,   # Worldwide FM presents : WOH Radio
    "101": 11,  # Carhartt WIP
    "387": 12,  # Beat Hotel x Ilegal Mezcal
    "388": 13,  # Passenger Presents: Ground Tempo
    "86": 14,   # Near Mint Record Store
    "87": 15,   # Love-Serve Bar
    "88": 16,   # Once In A Blue Moon
    "108": 17,  # Talks Tent
    "109": 18,  # The Knowledge
    "107": 19,  # booklove
    "105": 20,  # Craftwerk
    "395": 21,  # Craftwerk : Outdoors
    "106": 22,  # Lemon Lounge Workshops
    "104": 23,  # The Sanctuary Wider Activities
    "103": 24,  # Wellbeing Tent
    "389": 25,  # Wellness Tent : The Clearing
    "394": 26,  # Near Mint Record Signings
    "397": 27,  # Action Station
}

STAGE_NAMES = [
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

# The festival day runs ~09:00 to ~04:00 the following morning. Anything
# earlier than 09:00 is an after-midnight set and belongs to the previous
# day's listing, so it gets +24h - which is how data.json already stores them
# (max value 1680 = 4:00am).
DAY_START_MINUTES = 540

# Extraction runs inside the page. Returns [day, stageId, timeText, name].
EXTRACT_JS = """
() => {
  const rows = [];
  document.querySelectorAll('.scheduleCalendarWrap').forEach(wrap => {
    const day = wrap.dataset.scheduleDay;
    wrap.querySelectorAll('.scheduleCalendar__column[data-stage-id]').forEach(col => {
      const stageId = col.dataset.stageId;
      col.querySelectorAll('.scheduleCalendar__listing').forEach(listing => {
        const timeEl = listing.querySelector('.scheduleCalendar__performanceTime');
        const titleEl = listing.querySelector('h4');
        if (!timeEl || !titleEl) return;
        const time = timeEl.textContent.replace(/\\s+/g, ' ').trim();
        const name = titleEl.textContent.replace(/\\s+/g, ' ').trim();
        if (time && name) rows.push([day, stageId, time, name]);
      });
    });
  });
  return rows;
}
"""

TIME_RE = re.compile(
    r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*[-–—]\s*'
    r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)$',
    re.IGNORECASE,
)


# ---------------------------------------------------------------- scraping

def fetch_entries():
    """Scrape both schedule pages. Returns (entries, warnings)."""
    from playwright.sync_api import sync_playwright

    entries = []
    warnings = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for label, url in URLS:
            print(f"  loading {label} programme ...")
            page.goto(url, wait_until="networkidle", timeout=90000)
            page.wait_for_selector(".scheduleCalendarWrap", timeout=30000)
            rows = page.evaluate(EXTRACT_JS)
            wraps = page.eval_on_selector_all(
                ".scheduleCalendarWrap",
                "els => els.map(e => e.dataset.scheduleDay)",
            )
            print(f"    {len(wraps)} day blocks, {len(rows)} listings")
            if not rows:
                warnings.append(
                    f"{label}: page loaded but no listings found - markup may have changed"
                )
            for day, stage_id, time_text, name in rows:
                parsed = parse_time_range(time_text)
                if not parsed:
                    warnings.append(f"{label}: unparsed time {time_text!r} for {name!r}")
                    continue
                start, end = parsed
                entries.append({
                    "programme": label,
                    "date": site_day_to_iso(day),
                    "stage_id": stage_id,
                    "stage": STAGE_ID_TO_INDEX.get(stage_id),
                    "start": start,
                    "end": end,
                    "artist": name,
                    "time_text": time_text,
                })
        browser.close()

    unmapped = sorted({e["stage_id"] for e in entries if e["stage"] is None})
    if unmapped:
        warnings.append(
            "unmapped stage ids on the site (add them to STAGE_ID_TO_INDEX and "
            f"to STAGES in index.html): {', '.join(unmapped)}"
        )
    return entries, warnings


def site_day_to_iso(day):
    """'20/08/2026' -> '2026-08-20'."""
    d, m, y = day.split("/")
    return f"{y}-{m}-{d}"


def parse_time_range(text):
    m = TIME_RE.match(text.strip())
    if not m:
        return None
    start = to_minutes(m.group(1), m.group(2), m.group(3))
    end = to_minutes(m.group(4), m.group(5), m.group(6))
    if start < DAY_START_MINUTES:
        start += 1440
    if end < DAY_START_MINUTES:
        end += 1440
    if end < start:
        end += 1440
    return start, end


def to_minutes(hour, minute, meridiem):
    h = int(hour)
    mi = int(minute or 0)
    if meridiem.lower() == "pm" and h != 12:
        h += 12
    if meridiem.lower() == "am" and h == 12:
        h = 0
    return h * 60 + mi


# ---------------------------------------------------------------- matching

FILLER_RE = re.compile(
    r'\b(?:presents?|presented\sby|live|dj\sset|b2b|ft|feat|featuring|with|'
    r'very\sspecial\sguests?|special\sguests?|closing\sset|opening\sset)\b',
    re.IGNORECASE,
)


def normalize_name(name):
    base = name.lower().strip().replace("&amp;", "&").replace("&", " and ")
    stripped = ' '.join(re.sub(r'[^a-z0-9\s]', ' ', FILLER_RE.sub(" ", base)).split())
    if stripped:
        return stripped
    # Names made entirely of filler or punctuation ("Special Guest", "*") would
    # normalise to nothing and then never match anything. Keep them comparable.
    return ' '.join(re.sub(r'[^a-z0-9\s]', ' ', base).split()) or base.strip()


def name_score(a, b):
    """Similarity of two normalised names, 0-1.

    The site frequently wraps a name ("X" -> "Someone presents X (LIVE)"),
    which tanks a plain character ratio, so a clean containment of one name in
    the other is treated as a strong match in its own right.
    """
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    if a and b and (a in b or b in a):
        shorter, longer = sorted((len(a), len(b)))
        if shorter >= 3:
            ratio = max(ratio, 0.5 + 0.5 * (shorter / longer))
    return ratio


def fmt_minutes(m):
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def fmt_range(start, end):
    return f"{fmt_minutes(start)}-{fmt_minutes(end)}"


def stage_name(idx):
    if idx is None:
        return "unmapped stage"
    if 0 <= idx < len(STAGE_NAMES):
        return STAGE_NAMES[idx]
    return f"stage {idx}"


# ---------------------------------------------------------------- comparison

def match_day(local, site):
    """Pair up one day's local entries with the site's, most confident first.

    Name-only fuzzy matching was never going to be reliable on names like
    "Speakers Corner Quartet Celebrates The Music of Arthur Russell", so the
    stage and the slot do most of the work:

      pass 1  same stage, same start and end     - name only has to be close-ish
      pass 2  same stage, overlapping slot       - catches a moved time
      pass 3  same day, any stage, strong name   - catches a moved stage

    Anything still unpaired is genuinely new or genuinely gone.
    """
    local = [dict(x, _norm=normalize_name(x["artist"])) for x in local]
    site = [dict(x, _norm=normalize_name(x["artist"])) for x in site]
    matched = []
    lo, so = list(local), list(site)

    def run(pred, threshold):
        for s in list(so):
            best, best_ratio = None, 0.0
            for l in lo:
                if not pred(l, s):
                    continue
                ratio = name_score(s["_norm"], l["_norm"])
                if ratio > best_ratio:
                    best, best_ratio = l, ratio
            if best is not None and best_ratio >= threshold:
                matched.append((best, s))
                lo.remove(best)
                so.remove(s)

    same_stage = lambda l, s: s["stage"] is not None and l["stage"] == s["stage"]
    run(lambda l, s: same_stage(l, s)
        and l["start"] == s["start"] and l["end"] == s["end"], 0.55)
    run(lambda l, s: same_stage(l, s)
        and l["start"] < s["end"] and s["start"] < l["end"], 0.72)
    run(lambda l, s: True, 0.86)

    return {"matched": matched, "local_only": lo, "site_only": so}


def load_existing():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def compare(existing_days, scraped):
    """Match day by day, so a missing day is obvious instead of looking like
    a few hundred removals."""
    scraped_by_date = defaultdict(list)
    for e in scraped:
        scraped_by_date[e["date"]].append(e)

    report = {"days": [], "added": [], "removed": [], "time_changed": [],
              "stage_changed": [], "unknown_days": []}

    known_dates = {d.get("date") for d in existing_days}
    for date in sorted(set(scraped_by_date) - known_dates):
        report["unknown_days"].append(
            {"date": date, "count": len(scraped_by_date[date])}
        )

    for day in existing_days:
        date = day.get("date")
        label = f"{day.get('dn', '?')} {day.get('dd', '')}".strip()
        local = [
            {"start": ev[0], "end": ev[1], "stage": ev[2], "artist": ev[3]}
            for ev in day.get("ev", [])
        ]
        site = scraped_by_date.get(date, [])
        report["days"].append({
            "label": label, "date": date,
            "local": len(local), "site": len(site),
        })
        if not site:
            continue

        pairs = match_day(local, site)

        for l, s in pairs["matched"]:
            if l["start"] != s["start"] or l["end"] != s["end"]:
                report["time_changed"].append({
                    "day": label, "artist": l["artist"],
                    "stage": stage_name(l["stage"]),
                    "old": fmt_range(l["start"], l["end"]),
                    "new": fmt_range(s["start"], s["end"]),
                    "shift": s["start"] - l["start"],
                })
            if s["stage"] is not None and l["stage"] != s["stage"]:
                report["stage_changed"].append({
                    "day": label, "artist": l["artist"],
                    "old": stage_name(l["stage"]),
                    "new": stage_name(s["stage"]),
                })

        for s in pairs["site_only"]:
            report["added"].append({
                "day": label, "artist": s["artist"],
                "stage": stage_name(s["stage"]),
                "time": fmt_range(s["start"], s["end"]),
            })

        for l in pairs["local_only"]:
            report["removed"].append({
                "day": label, "artist": l["artist"],
                "stage": stage_name(l["stage"]),
                "time": fmt_range(l["start"], l["end"]),
            })

    return report


# ---------------------------------------------------------------- reporting

def show(items, heading, line, limit=40):
    if not items:
        return
    print(f"\n{heading} ({len(items)})")
    for it in items[:limit]:
        print("  " + line(it))
    if len(items) > limit:
        print(f"  ... and {len(items) - limit} more")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", metavar="FILE",
                    help="write the scraped entries to FILE")
    args = ap.parse_args()

    print("Fetching official set times ...")
    try:
        scraped, warnings = fetch_entries()
    except Exception as exc:
        print(f"\nCould not scrape the site: {exc}")
        return 1

    print(f"\nScraped {len(scraped)} listings in total.")
    for w in warnings:
        print(f"  ! {w}")

    if not scraped:
        print("Nothing scraped - stopping rather than reporting false removals.")
        return 1

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(scraped, f, indent=2, ensure_ascii=False)
        print(f"Scraped entries written to {args.json}")

    try:
        existing = load_existing()
    except FileNotFoundError:
        print(f"{DATA_FILE} not found.")
        return 1
    except json.JSONDecodeError as exc:
        print(f"Could not parse {DATA_FILE}: {exc}")
        return 1

    report = compare(existing, scraped)

    print("\n" + "=" * 64)
    print("SET TIMES CHECK")
    print("=" * 64)

    print("\nPer day (app vs site):")
    empty_days = []
    for d in report["days"]:
        flag = ""
        if d["site"] == 0:
            flag = "  <- nothing scraped for this day"
            empty_days.append(d["label"])
        print(f"  {d['label']:<8} {d['date']}   app {d['local']:>3}   site {d['site']:>3}{flag}")

    for u in report["unknown_days"]:
        print(f"  ! site has a day the app doesn't: {u['date']} ({u['count']} listings)")

    if empty_days:
        print(f"\nNo listings scraped for: {', '.join(empty_days)}.")
        print("Removals for those days are suppressed - fix the scrape first.")
        report["removed"] = [
            r for r in report["removed"] if r["day"] not in empty_days
        ]

    show(report["added"], "NEW ON THE SITE",
         lambda a: f"{a['day']}  {a['time']}  {a['stage']}  {a['artist']}")
    show(report["removed"], "IN THE APP BUT NOT ON THE SITE",
         lambda r: f"{r['day']}  {r['time']}  {r['stage']}  {r['artist']}")
    show(report["time_changed"], "TIME CHANGES",
         lambda t: f"{t['day']}  {t['artist']}  {t['old']} -> {t['new']}"
                   f"  ({t['shift']:+d} min)")
    show(report["stage_changed"], "STAGE CHANGES",
         lambda s: f"{s['day']}  {s['artist']}  {s['old']} -> {s['new']}")

    changes = sum(len(report[k]) for k in
                  ("added", "removed", "time_changed", "stage_changed"))
    if changes == 0:
        print("\nNo changes - the app matches the official site.")
    else:
        print(f"\n{changes} difference(s) to review, then edit data.json.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
