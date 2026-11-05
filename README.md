# JeffKagle.github.io

Personal website — https://jeffreykagle.com

- `data/site.json` — all projects, publications, and updates (single source of truth)
- `index.html` — homepage; project cards link to each project's document
- `portfolio.html` — portfolio built from projects marked for it; also exported as `assets/portfolio.pdf`
- `assets/docs/` — project documents, stored unmodified
- `assets/img/<project>/` — cover images and figures pulled from each document
- `tools/ingest.py` — brings in a new document and extracts figures
- `tools/build.py` — regenerates the pages and PDF and checks for broken links and errors

Workflow details are in `CLAUDE.md`.
