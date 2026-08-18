# We Out Here 2026 — Melomaniacs set-time planner

Offline-first PWA listing every set at We Out Here 2026. Built by Bitasuite for
the Melomaniacs. Free, no sign-up, no app store, works with no signal.

- **Live:** https://melomaniacs.pages.dev (Cloudflare Pages, auto-deploys from `main`)
- **Repo:** https://github.com/bitasuite-music/we-out-here-2026
- **Local:** `~/Consultancy Hub/Bitasuite/We Out Here 2026/we-out-here-2026`
- **Festival:** 20–23 August 2026, Wimborne St Giles, Dorset

## Verified facts (check before quoting these anywhere)

Counted from `data.json`, 17 Aug 2026 — **not** from memory or old marketing copy:

| Thing | Value |
|---|---|
| Sets / sessions | **748** |
| Areas | **28** (all 28 in use across the weekend) |
| Days | 4 (Thu 20 – Sun 23 Aug) |
| Melomaniacs' own set | **Brawnswood**, Thursday 22:00–00:00 |

Spelling: the stage is **Brawnswood**, not "Brownswood" (that's Gilles
Peterson's label — easy and embarrassing to mix up).

Live colours, from the CSS custom properties in `index.html`:

| Role | Var | Hex |
|---|---|---|
| Background | `--bg` | `#0f0d12` |
| Card | `--card` | `#1c1826` |
| Teal accent | `--acc2` | `#5ad9c8` |
| Pink accent | `--acc` | `#ef6fae` |
| Gold | `--gold` | `#ffc861` |
| Text | `--ink` | `#f5f1f7` |
| Live/urgent | `--live` | `#ff5f57` |

Channels: `mixcloud.com/MelomaniacsCollective`,
`instagram.com/mel0maniacs` (**a zero, not an "o"**),
`instagram.com/godfrey_phil` (Bitasuite).

## Architecture — the one thing that catches everyone

`index.html` is the whole app: inline CSS, inline JS, and **the schedule inline
as `var DATA`**. `data.json` is only the scraper's snapshot for diffing.

> **Editing `data.json` alone changes nothing in the app.** Both have to be
> updated together. `extract_data.py` describes a fetch-based rewrite that was
> never finished — ignore it.

`ev` rows are `[startMinutes, endMinutes, stageIndex, name]`. Minutes run past
1440 for after-midnight sets (max 1680 = 04:00). Anything under 540 (09:00) is
a next-morning set and gets +1440.

## Release procedure

```bash
python3 check-updates.py            # diff the live site against data.json
# apply any real changes to BOTH data.json and var DATA in index.html
python3 build_pdfs.py               # PDFs + dated filenames + link rewrite + VER bump
git add -A && git commit -m "..." && git push
```

`build_pdfs.py` is the release command. It rebuilds both PDFs, writes
date-stamped copies, rewrites `PDF_SET`/`PDF_WIDER` in `index.html`, updates
`ASSETS` in `sw.js`, and bumps `VER`. Don't hand-edit those.

Update `SCRAPED` in `index.html` when the data changes — it stamps the app
banner and both PDF footers from one place.

## Traps already hit (don't rediscover these)

**The scraper.** `body.innerText` only returns the *visible* day tab, so three
days out of four came back empty and every artist on them looked "removed".
All four days are in the DOM at once inside
`.scheduleCalendarWrap[data-schedule-day]` — read the DOM, never click tabs.
There are **two** schedule pages: `/set-times/` and
`/wider-programme-set-times/`. Scrape both.

**Star keys embed the start time.** `eid(d,e)` is `day|stage|startMinutes`, so
moving a set silently detaches its star — nothing looks broken, the star is
just gone. When times change, add the old→new key pairs to `FAVMOVED` in
`index.html`. `pruneFav()` then drops stars for cancelled sets so the My Plan
badge can't count sets it will never show.

**The service worker is cache-first.** A stale hit is served before the network
is consulted, and `activate()` only clears caches whose name differs from
`CACHE`. So:
- Bumping `VER` is the *only* thing that refreshes cached assets.
- `?v=2` does **not** work against it — the fetch handler matches with
  `ignoreSearch: true`, so query strings are ignored.
- The app itself is always one load behind: load one serves the old
  `index.html`, load two is current. The pill offers a refresh when it detects
  a version change.

**PDF links open outside the service worker.** `<base target="_blank">` plus
`target="_blank"` hands the URL to a new top-level context — in an installed
iOS PWA that's Safari, with its own HTTP cache the worker cannot touch. This is
why rebuilt PDFs under the same name kept showing up stale. Fixed by
date-stamping the filenames; the stable names are kept as identical copies so a
cached older `index.html` still gets current times rather than a 404.

**Never overwrite a web asset in place.** Same reason. New content, new
filename. The logo is `melomaniacs-240.gif` for exactly this reason.

**The desktop bridge cannot delete files.** `rm` returns "Operation not
permitted". So **do not run git through `device_bash`** — every `git status`
creates `.git/index.lock`, fails to remove it, and the stale lock then blocks
VS Code with "Another git process seems to be running". If it happens, `mv` the
lock out of `.git/` (mv works, rm doesn't). Run git in the cloud container or
Phil's own terminal instead.

**Re-stage before editing.** `device_stage_files` snapshots are point-in-time.
Reusing an earlier turn's snapshot silently reverts work. Always re-stage
`index.html`, `sw.js` and `build_pdfs.py` before patching them.

## The logo

`melomaniacs-240.gif` — 240px, 60 frames, 3.6s loop, 194KB (was 304px/120
frames/541KB). It's a **coin flip** between outline and solid lettering, not a
rotation, so frames carry real content and can't be cut hard. It is **84%
transparent** — never flatten it, the easter-egg overlay uses `drop-shadow`.

240px is deliberate: the overlay renders it at **120px**, so 2× for retina.
Also used at 58px (footer) and 23px (rows). Anything smaller than 240 breaks
the overlay.

Animated WebP was tested and is **worse** for this content — 293KB vs GIF's
167KB at equal frames. Don't retry it.

Easter egg: five taps on any logo (matched on `src === LOGO`, so new
placements are covered automatically) or on a Melomaniacs card fires
`showSpinningLogo()`. Resets after 2.5s of no taps.

## PDFs

A4 landscape. Set times = 4 days × 2 sides (6 main stages / the other 11
areas); wider programme = 1 page per day (11 areas). No horizontal rules — each
box states its own times and hour labels run down both edges. White boxes with
a coloured left rule, not shaded fills: less ink, readable in greyscale.

Box heights follow the text, not the clock. A 15-minute author signing cannot
fit a 50-character title in its slot, so each column is packed in time order
and dense clusters drift a few minutes low. The alternative was cutting names
off. Verify after every build: **748 sets, 0 clipped, 0 collisions, 0
overflow**.

## Known, not urgent

- Artist names are stripped of accents in `data.json` — the site has `ROGÊ`,
  `C-sé`, `Iko Chérie`, `LÉNA C`. The scraper's matcher ignores accents so it
  never flags them.
- Four names are deliberately shorter than the official titles (`MMM: The
  Radical Bookshelf` etc). `check-updates.py` lists these separately under
  "same slot, different name" — expected, not a change to action.
- `Melos gif.gif` (the old 541KB logo) may still be tracked; `git rm` it.
