#!/usr/bin/env python3
"""Build and bug-check jeffreykagle.com.

    python3 tools/build.py              # render pages, run all checks, regenerate portfolio PDF if needed
    python3 tools/build.py --no-browser # skip the headless-Chrome checks and PDF (fast)
    python3 tools/build.py --force-pdf  # regenerate assets/portfolio.pdf even if nothing changed

What it does:
  1. Validates data/site.json (required fields, unique ids, files exist, document checksums).
  2. Fills the <!-- BUILD:name --> regions in index.html and portfolio.html.
  3. Checks every local href/src on both pages points at a real file / anchor.
  4. Loads both pages in headless Chrome (desktop + phone width): console errors, failed
     requests, broken images, horizontal overflow. Screenshots go to /tmp/site-check/.
  5. Prints portfolio.html to assets/portfolio.pdf when its inputs changed.
Exits non-zero if any error is found. Do not push when it fails.
"""
import argparse
import functools
import hashlib
import html
import http.server
import json
import re
import subprocess
import sys
import threading
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "site.json"
PAGES = ["index.html", "portfolio.html"]
PDF = ROOT / "assets" / "portfolio.pdf"
PDF_HASH = ROOT / "data" / "portfolio-pdf-inputs.sha256"
CHECK_DIR = Path("/tmp/site-check")
MAX_IMAGE_KB = 600

errors, warnings = [], []


def err(msg): errors.append(msg)
def warn(msg): warnings.append(msg)
def esc(s): return html.escape(str(s), quote=True)
def href(path): return esc(quote(path, safe="/:#?=&%"))
def sha256(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rich(s):
    """Escape text but allow <sub>, <sup>, <i>, <b> for variable names in write-ups."""
    out = esc(s)
    for tag in ("sub", "sup", "i", "b"):
        out = out.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    return out


# ───────────────────────── validation ─────────────────────────

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def date_key(p):
    """Sort key (year, month) from 'sort_date' (YYYY-MM) or the display date ('Dec 2024', 'May 2025', '2026').
    A year with no month sorts after dated projects of the same year."""
    raw = str(p.get("sort_date") or p.get("date") or "")
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", raw.strip())
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.fullmatch(r"(?:([A-Za-z]{3})[a-z]*\.?\s+)?(\d{4})", raw.strip())
    if not m:
        return None
    return (int(m.group(2)), MONTHS.get((m.group(1) or "").lower(), 0))


def sorted_projects(data):
    """Newest first. Ties keep the order in site.json."""
    return sorted(data.get("projects", []), key=lambda p: date_key(p) or (0, 0), reverse=True)


def all_docs(p):
    """Primary document (cover image links to it) + any extra_documents (poster, slides, ...)."""
    return ([p["document"]] if p.get("document") else []) + list(p.get("extra_documents") or [])


def check_file(path, where, kind="file"):
    if not path:
        err(f"{where}: missing {kind} path")
        return False
    if re.match(r"^[a-z]+:", path):
        return True  # external URL
    if not (ROOT / path).is_file():
        err(f"{where}: {kind} not found: {path}")
        return False
    return True


def validate(data):
    ids = set()
    for i, p in enumerate(data.get("projects", [])):
        where = f"projects[{i}] ({p.get('id', '?')})"
        for field in ("id", "title", "tag", "date", "summary"):
            if not p.get(field):
                err(f"{where}: missing '{field}'")
        pid = p.get("id", "")
        if p.get("date") and date_key(p) is None:
            err(f"{where}: date '{p['date']}' not understood — use 'Mon YYYY' or 'YYYY', or add sort_date 'YYYY-MM'")
        if pid in ids:
            err(f"{where}: duplicate id '{pid}'")
        ids.add(pid)
        if pid and not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", pid):
            err(f"{where}: id must be lowercase-with-dashes")
        if p.get("cover"):
            check_file(p["cover"], where, "cover image")
        else:
            warn(f"{where}: no cover image (card shows a placeholder)")
        if not p.get("document"):
            warn(f"{where}: no document attached")
        for doc in all_docs(p):
            if check_file(doc.get("file"), where, "document"):
                want = doc.get("sha256")
                got = sha256(ROOT / doc["file"])
                if not want:
                    err(f"{where}: document has no sha256 recorded (expected {got})")
                elif want != got:
                    err(f"{where}: DOCUMENT CHANGED — {doc['file']} no longer matches the uploaded original")
        pf = p.get("portfolio") or {}
        if pf.get("include"):
            if not pf.get("overview"):
                err(f"{where}: portfolio.include is true but portfolio.overview is empty")
            for j, f in enumerate(pf.get("figures", [])):
                check_file(f.get("src"), f"{where} figure {j + 1}", "figure")
                if not f.get("caption"):
                    warn(f"{where} figure {j + 1}: no caption")
            for s_i, sec in enumerate(pf.get("sections", [])):
                if not sec.get("heading"):
                    err(f"{where} section {s_i + 1}: missing heading")
                for blk in sec.get("blocks", []):
                    if "equation" in blk:
                        check_file(blk["equation"], f"{where} section {s_i + 1}", "equation")
            for j, m in enumerate(pf.get("metrics", [])):
                if not (m.get("value") and m.get("label")):
                    err(f"{where} metric {j + 1}: needs 'value' and 'label'")
    for i, pub in enumerate(data.get("publications", [])):
        where = f"publications[{i}]"
        for field in ("title", "venue", "authors"):
            if not pub.get(field):
                err(f"{where}: missing '{field}'")
        if pub.get("file"):
            check_file(pub["file"], where, "file")
        elif not pub.get("url"):
            warn(f"{where}: no file or url — no download button")
    # oversized images slow the site down
    for img in (ROOT / "assets" / "img").rglob("*"):
        if img.is_file() and img.stat().st_size > MAX_IMAGE_KB * 1024:
            warn(f"large image ({img.stat().st_size // 1024} KB): {img.relative_to(ROOT)} — run tools/ingest.py image")


# ───────────────────────── rendering ─────────────────────────

def bold_owner(names, owner):
    return esc(names).replace(esc(owner), f"<strong>{esc(owner)}</strong>")


def render_updates(data):
    out = []
    for u in data.get("updates", []):
        out.append(f'      <li><span class="update-date">{esc(u["date"])}</span><span>{esc(u["text"])}</span></li>')
    return "\n".join(out)


def render_cards(data):
    out = []
    for p in sorted_projects(data):
        doc = p.get("document")
        pf = (p.get("portfolio") or {}).get("include")
        if p.get("cover"):
            visual = f'<img src="{href(p["cover"])}" alt="{esc(p.get("cover_alt") or p["title"])}" class="project-img" loading="lazy" />'
        else:
            visual = f'<div class="project-img-placeholder"><span>{esc(p["tag"])}</span></div>'
        if doc:
            cover = (f'<a class="project-cover" href="{href(doc["file"])}" target="_blank" rel="noopener" '
                     f'title="Open the full document (PDF)">{visual}<span class="project-cover-badge">↓ PDF</span></a>')
        else:
            cover = visual
        actions = []
        for d in all_docs(p):
            actions.append(f'<a class="btn btn-sm" href="{href(d["file"])}" target="_blank" rel="noopener">↓ {esc(d.get("label") or "Document")}</a>')
        if pf:
            actions.append(f'<a class="btn btn-sm" href="portfolio.html#{esc(p["id"])}">Portfolio →</a>')
        out.append(f"""      <article class="project-card" id="project-{esc(p['id'])}">
        {cover}
        <div class="project-body">
          <p class="project-tag">{esc(p['tag'])} · {esc(p['date'])}</p>
          <h3 class="project-title">{esc(p['title'])}</h3>
          <p class="project-desc">{esc(p['summary'])}</p>
          <div class="project-actions">{''.join(actions)}</div>
        </div>
      </article>""")
    if not out:
        out.append('      <p class="empty-note">Projects coming soon.</p>')
    return "\n".join(out)


def render_publications(data):
    owner = data.get("owner", "")
    out = []
    for pub in data.get("publications", []):
        link = pub.get("file") or pub.get("url")
        label = "↓ PDF" if pub.get("file") else "↗ Link"
        btn = f'<a href="{href(link)}" class="btn" target="_blank" rel="noopener">{label}</a>' if link else ""
        out.append(f"""      <div class="pub-item">
        <div class="pub-meta">
          <p class="pub-venue">{esc(pub['venue'])}</p>
          <h3 class="pub-title">{esc(pub['title'])}</h3>
          <p class="pub-authors">{bold_owner(pub['authors'], owner)}</p>
        </div>
        {btn}
      </div>""")
    if not out:
        out.append('      <p class="empty-note">Publications coming soon.</p>')
    return "\n".join(out)


def render_figure(f, n):
    cls = "pf-figure wide" if f.get("wide") else "pf-figure"
    cap = esc(f.get("caption", ""))
    return (f'<figure class="{cls}"><img src="{href(f["src"])}" alt="{cap}" loading="lazy" />'
            f'<figcaption><b>Fig. {n}.</b> {cap}</figcaption></figure>')


def render_portfolio(data):
    owner = data.get("owner", "")
    site = data.get("site_url", "").rstrip("/")
    out = []
    for p in sorted_projects(data):
        pf = p.get("portfolio") or {}
        if not pf.get("include"):
            continue
        meta = " · ".join(esc(x) for x in (p["tag"], p["date"], p.get("context")) if x)
        parts = [f'    <p class="pf-meta">{meta}</p>',
                 f'    <h2 class="pf-title">{esc(p["title"])}</h2>']
        if p.get("team"):
            parts.append(f'    <p class="pf-team">{bold_owner(p["team"], owner)}</p>')
        parts.append(f'    <p class="pf-overview">{esc(pf["overview"])}</p>')
        docs = all_docs(p)
        if docs:
            links = "".join(f'<a class="btn" href="{href(site + "/" + d["file"])}" target="_blank" rel="noopener">'
                            f'↓ {esc(d.get("label") or "PDF")}</a>' for d in docs)
            parts.append(f'    <div class="pf-docs">{links}</div>')
        if pf.get("metrics"):
            tiles = "".join(f'<div class="pf-metric"><span class="pf-metric-value">{esc(m["value"])}</span>'
                            f'<span class="pf-metric-label">{esc(m["label"])}</span></div>' for m in pf["metrics"])
            parts.append(f'    <div class="pf-metrics">{tiles}</div>')
        figs = pf.get("figures", [])
        if figs:  # lead figure, full width, right after the headline numbers
            parts.append(f'    <div class="pf-figures lead">{render_figure(figs[0], 1)}</div>')
        if pf.get("results"):
            items = "".join(f"<li>{rich(r)}</li>" for r in pf["results"])
            heading = esc(pf.get("results_heading") or "Key results")
            parts.append(f'    <h3 class="pf-subhead">{heading}</h3>\n    <ul class="pf-results">{items}</ul>')
        for sec in pf.get("sections", []):  # written write-ups, e.g. a model derivation
            parts.append(f'    <h3 class="pf-subhead">{esc(sec["heading"])}</h3>')
            for blk in sec.get("blocks", []):
                if "text" in blk:
                    parts.append(f'    <p class="pf-text">{rich(blk["text"])}</p>')
                elif "equation" in blk:
                    parts.append(f'    <div class="pf-eq"><img src="{href(blk["equation"])}" alt="{esc(blk.get("alt", "equation"))}" /></div>')
        if len(figs) > 1:
            rest = "".join(render_figure(f, i + 2) for i, f in enumerate(figs[1:]))
            parts.append(f'    <div class="pf-figures">{rest}</div>')
        out.append(f'  <section class="pf-item" id="{esc(p["id"])}">\n' + "\n".join(parts) + "\n  </section>")
    if not out:
        out.append('  <section class="pf-item"><p class="empty-note">Portfolio entries coming soon.</p></section>')
    return "\n\n".join(out)


def fill(text, name, body, page):
    pat = re.compile(rf"(<!-- BUILD:{name} -->\n)(.*?)(<!-- /BUILD:{name} -->)", re.S)
    if not pat.search(text):
        err(f"{page}: BUILD:{name} markers missing")
        return text, None
    old = pat.search(text).group(2)
    new_body = body + "\n" if body else ""
    return pat.sub(lambda m: m.group(1) + new_body + m.group(3), text), old


# ───────────────────────── static link check ─────────────────────────

def static_links():
    ids = {pg: set(re.findall(r'\sid="([^"]+)"', (ROOT / pg).read_text())) for pg in PAGES}
    for pg in PAGES:
        text = (ROOT / pg).read_text()
        for attr, val in re.findall(r'\s(href|src)="([^"]+)"', text):
            val = html.unescape(val)
            u = urlparse(val)
            if u.scheme in ("http", "https"):
                if u.netloc.endswith("jeffreykagle.com") and u.path.strip("/"):
                    path = unquote(u.path.lstrip("/"))
                    if not (ROOT / path).is_file() and path != "assets/portfolio.pdf":
                        err(f"{pg}: absolute link to missing file: {val}")
                continue
            if u.scheme in ("mailto", "tel", "data", "javascript"):
                continue
            target = unquote(u.path) or pg
            if target != "assets/portfolio.pdf" and not (ROOT / target).is_file():
                err(f"{pg}: broken {attr}: {val}")
            if u.fragment and target in ids and u.fragment not in ids[target]:
                err(f"{pg}: link to missing anchor: {val}")


# ───────────────────────── browser checks + PDF ─────────────────────────

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


def serve():
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def launch(p):
    for kw in ({}, {"channel": "chrome"}, {"executable_path": "/usr/bin/google-chrome"}):
        try:
            return p.chromium.launch(**kw)
        except Exception:
            continue
    raise RuntimeError("could not launch Chrome/Chromium for checks")


LOAD_ALL_IMAGES = """async () => {
  for (const img of document.images) img.loading = 'eager';
  await Promise.all([...document.images].map(i => i.complete ? 0 :
    new Promise(r => { i.onload = i.onerror = r; })));
  return [...document.images].filter(i => !i.naturalWidth).map(i => i.getAttribute('src'));
}"""


def pdf_inputs_hash():
    h = hashlib.sha256()
    h.update((ROOT / "portfolio.html").read_bytes())
    h.update((ROOT / "assets" / "style.css").read_bytes())
    for src in sorted(set(re.findall(r'src="([^"]+)"', (ROOT / "portfolio.html").read_text()))):
        f = ROOT / unquote(html.unescape(src))
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()


def browser_checks(make_pdf, force_pdf):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        warn("playwright not installed — skipped browser checks (pip install playwright)")
        return
    CHECK_DIR.mkdir(parents=True, exist_ok=True)
    srv, base = serve()
    try:
        with sync_playwright() as p:
            browser = launch(p)
            for pg in PAGES:
                for name, vw in (("desktop", {"width": 1280, "height": 800}), ("phone", {"width": 390, "height": 844})):
                    page = browser.new_page(viewport=vw)
                    problems = []
                    page.on("console", lambda m: problems.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
                    page.on("pageerror", lambda e: problems.append(f"script error: {e}"))
                    page.on("response", lambda r: problems.append(f"HTTP {r.status}: {r.url}")
                            if r.status >= 400 and r.url.startswith(base) else None)
                    page.on("requestfailed", lambda r: problems.append(f"request failed: {r.url}")
                            if r.url.startswith(base) else None)
                    page.goto(f"{base}/{pg}", wait_until="networkidle")
                    broken = page.evaluate(LOAD_ALL_IMAGES)
                    problems += [f"broken image: {b}" for b in broken]
                    if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
                        problems.append("page is wider than the screen (horizontal scroll)")
                    page.screenshot(path=str(CHECK_DIR / f"{pg.replace('.html', '')}-{name}.png"), full_page=True)
                    for prob in problems:
                        # a missing portfolio.pdf before the first build is expected
                        if "portfolio.pdf" in prob and not PDF.exists():
                            continue
                        err(f"{pg} [{name}]: {prob}")
                    page.close()

            if make_pdf:
                digest = pdf_inputs_hash()
                stale = force_pdf or not PDF.exists() or not PDF_HASH.exists() or PDF_HASH.read_text().strip() != digest
                if stale:
                    page = browser.new_page()
                    page.goto(f"{base}/portfolio.html", wait_until="networkidle")
                    page.evaluate(LOAD_ALL_IMAGES)
                    page.emulate_media(media="print")
                    page.pdf(path=str(PDF), print_background=True, prefer_css_page_size=True)
                    page.close()
                    PDF_HASH.write_text(digest + "\n")
                    print(f"  wrote {PDF.relative_to(ROOT)}")
                else:
                    print("  portfolio PDF up to date")
            browser.close()
    finally:
        srv.shutdown()
    if make_pdf and PDF.exists():
        info = subprocess.run(["pdfinfo", str(PDF)], capture_output=True, text=True).stdout
        m = re.search(r"Pages:\s+(\d+)", info)
        if not m or int(m.group(1)) < 1:
            err("assets/portfolio.pdf is empty or unreadable")
        else:
            print(f"  portfolio PDF: {m.group(1)} page(s), {PDF.stat().st_size // 1024} KB")


# ───────────────────────── main ─────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-browser", action="store_true", help="skip headless Chrome checks and PDF")
    ap.add_argument("--force-pdf", action="store_true", help="always regenerate the portfolio PDF")
    args = ap.parse_args()

    try:
        data = json.loads(DATA.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: data/site.json is not valid JSON: {e}")
        sys.exit(1)

    print("1/5 validating data/site.json")
    validate(data)

    print("2/5 rendering pages")
    idx = (ROOT / "index.html").read_text()
    idx, _ = fill(idx, "updates", render_updates(data), "index.html")
    idx, _ = fill(idx, "projects", render_cards(data), "index.html")
    idx, _ = fill(idx, "publications", render_publications(data), "index.html")
    (ROOT / "index.html").write_text(idx)

    pf = (ROOT / "portfolio.html").read_text()
    pf, old_body = fill(pf, "portfolio", render_portfolio(data), "portfolio.html")
    new_body = re.search(r"<!-- BUILD:portfolio -->\n(.*?)<!-- /BUILD:portfolio -->", pf, re.S)
    changed = old_body is None or new_body is None or old_body != new_body.group(1)
    if changed or "pf-updated" not in pf:
        stamp = date.today().strftime("%B %Y")
        pf, _ = fill(pf, "updated", f'    <p class="pf-updated no-print">Last updated {stamp}</p>', "portfolio.html")
    (ROOT / "portfolio.html").write_text(pf)

    print("3/5 checking local links")
    static_links()

    if args.no_browser:
        print("4/5 browser checks skipped\n5/5 PDF skipped")
    else:
        print("4/5 headless Chrome checks (desktop + phone)")
        print("5/5 portfolio PDF")
        browser_checks(make_pdf=True, force_pdf=args.force_pdf)

    for w in warnings:
        print(f"  warning: {w}")
    if errors:
        print(f"\nFAILED — {len(errors)} problem(s):")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    print(f"\nOK — no problems found. Screenshots: {CHECK_DIR}")


if __name__ == "__main__":
    main()
