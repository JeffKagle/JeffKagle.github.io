# jeffreykagle.com — how this site is maintained

Static site on GitHub Pages (custom domain in `CNAME`, `.nojekyll` so files are served as-is).
All project/publication content lives in `data/site.json`; `tools/build.py` writes it into the
`<!-- BUILD:... -->` regions of `index.html` and `portfolio.html` and regenerates `assets/portfolio.pdf`.
Never hand-edit inside BUILD regions — edit the data file and rebuild.

## Rules
- Only add material the owner (Jeffrey) explicitly says is for the website or portfolio. Other people
  use the Claude account this repo is connected to; anything not clearly marked for the site stays out.
- Never modify an uploaded document. PDFs are stored byte-for-byte; other formats are converted to PDF
  only. Each document's sha256 is recorded in site.json and `build.py` fails if a file changes.
- Always run `python3 tools/build.py` before pushing and only push when it prints OK. Look at the
  screenshots in /tmp/site-check/ for anything that looks wrong.
- Push straight to `main` (owner approved). Commit message: what was added/changed.

## Adding a project (owner sends a document + a short description)
1. `python3 tools/ingest.py doc <upload> <slug>` — stores `assets/docs/<slug>.pdf`, prints sha256,
   candidate figures, page contact sheets, and a JSON stub.
2. Read the document. Pick a cover image and the major figures (results first). Save them with
   `ingest.py image` (extracted bitmaps/photos) or `ingest.py crop` (vector plots, multi-panel figures).
3. Add the stub to `projects` in `data/site.json` (pages sort newest-first by `date`; use "Mon YYYY" or add `sort_date` "YYYY-MM") and fill it in from the owner's
   description plus the document:
   - `document` is the main file (the card image links to it). A second file for the same project
     (poster, slides) goes in `extra_documents` with its own label + sha256 — ingest it with its own
     slug, e.g. `<slug>-poster`, and use `crop --doc <slug>-poster` to take figures from it.
   - `summary`: 1–2 sentences for the projects-page card (what it is + headline result).
   - `portfolio.include`: true only if the owner said it is for the portfolio.
   - `portfolio.overview`: 2–3 sentences, problem → approach → outcome.
   - `portfolio.metrics`: 2–4 headline numbers from the document (value + short label). Use only
     numbers that appear in the document; never round in a way that changes the claim.
   - `portfolio.results`: 3–5 concrete findings, results-first wording.
   - `portfolio.figures`: major figures with captions and `source_page`; first one is shown large.
   - Theory/literature projects: `portfolio.results_heading` (e.g. "Key contributions") and
     `portfolio.sections` = [{heading, blocks: [{text} | {equation, alt}]}] for a written model
     section; typeset equations with `ingest.py equation`. Text may use <sub>/<sup>/<i>/<b>.
   - Prefer the owner's own figures. Don't feature figures reproduced from other people's papers;
     if a document has none, ask — an AI illustration is OK only if labeled as AI-generated on the
     image and in the caption.
4. If it is a paper/report, also add it to `publications` (owner's name gets bolded automatically).
5. `python3 tools/build.py`, check screenshots, commit, push. Tell the owner what was added and
   anything in the summary they should verify.
