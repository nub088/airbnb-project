# Accommodation Finder

A little project about a fun problem: given a short-term rental listing, can you figure out
who actually operates it just from the photos? Turns out you often can. The same photos a
management company posts on a booking platform usually show up on their own website too, so
if you reverse-image-search a listing's pictures and see where else they land, the operator
tends to fall out of it.

This automates that. Point it at a listing, it pulls the photos, runs them through a couple
of reverse-image-search engines, correlates the matches, and tells you which company is
behind the unit — with the links it used to decide, so you can check its work.

## How it works

Give it a listing URL or ID and it:

1. Downloads the listing's photos.
2. Reverse-image-searches each one on **Yandex Images** and **Google Lens**.
3. Looks at where the same photos turn up elsewhere and works out the operating company from
   the overlap.
4. Scrapes that operator's own site for their contact details.
5. Writes a row per listing to `results.csv`, including the evidence links.

## How it's built

It uses the WAT layout I like — plain-English workflows describe the steps, and the actual
work happens in small Python scripts:

```
workflows/        — the steps, written out in markdown
tools/            — the scripts (download photos, run searches, append CSV)
run.py            — runs the whole thing end to end, no model needed
.tmp/             — per-listing scratch space (photos, intermediate JSON)
browser-profile/  — a Firefox profile that keeps you logged in between runs
results.csv       — the output, appended to
```

`run.py` just chains the tools in order, so a run is reproducible and I can re-run a single
piece without redoing everything.

## Setup

```bash
pip install playwright requests
playwright install firefox
```

Then seed the browser profile once:

```bash
./tools/setup_firefox_profile.sh
```

That opens Firefox with a persistent profile — log in, close the window, and the session
sticks around in `./browser-profile/` for every future run. Worth also logging into a Google
account in that same window; it cuts down on Google Lens captchas a lot.

## Using it

```bash
# one listing
python run.py --listing-id 1353198002579642941

# top 10 from a search page
python run.py --search-url "<search-url>" --top-n 10

# skip Google Lens (faster, dodges the captchas)
python run.py --search-url "..." --yandex-only

# re-run on photos you already pulled
python run.py --listing-id 1353198002579642941 --skip-download

# no browser window
python run.py --listing-id 1353198002579642941 --headless
```

Results go to `results.csv` and `.tmp/<listing-id>/result.json`. The main columns are the
resolved `operator`, its `operator_phone` / `operator_email`, a `managed_yn` flag
(MANAGED / OWNER / UNKNOWN), and `evidence_urls` — the cross-platform hits that drove the
match, so you can sanity-check it yourself.

## The annoying parts

- **Google Lens** doesn't love being driven by Playwright and will throw a captcha now and
  then. When it does, the script stops and waits for you to solve it in the window, then
  carries on. Use `--yandex-only` if you're running it unattended — Yandex behaves.
- Operator detection leans on a keyword list, so brands it doesn't recognize come back as
  `UNKNOWN`. That's what `evidence_urls` is for — open them and it's usually obvious.
- Photos load as you scroll, so really big listings (30+ photos) might not all load in the
  scroll loop. Bump `--photos` if you need to go deeper.

## Test listing

`1353198002579642941` — the Valencia "Green & Natural Apartment" — is my go-to test. Photos 3
and 4 are the distinctive ones; photo 1 is a stock architecture shot that shows up on tons of
listings, which makes it a good check that it's not throwing false positives. It should come
back as `MANAGED`, operator Travel Habitat, unit VA077-2.
