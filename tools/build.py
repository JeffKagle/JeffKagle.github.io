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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portfolio_scene  # noqa: E402

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
    for i, v in enumerate(data.get("visualizations", [])):
        for field in ("title", "src", "caption"):
            if not v.get(field):
                err(f"visualizations[{i}]: missing '{field}'")
        if v.get("src"):
            check_file(v["src"], f"visualizations[{i}]", "animation")
        if v.get("project") and v["project"] not in {p.get("id") for p in data.get("projects", [])}:
            err(f"visualizations[{i}]: unknown project '{v['project']}'")
    for i, m in enumerate(data.get("in_preparation", [])):
        if not m.get("title"):
            err(f"in_preparation[{i}]: missing 'title'")
    for i, w in enumerate(data.get("writing", [])):
        where = f"writing[{i}]"
        for field in ("title", "venue", "summary", "file", "sha256"):
            if not w.get(field):
                err(f"{where}: missing '{field}'")
        if w.get("date") and date_key(w) is None:
            err(f"{where}: date '{w['date']}' not understood")
        if w.get("file") and check_file(w["file"], where, "document") and w.get("sha256"):
            if sha256(ROOT / w["file"]) != w["sha256"]:
                err(f"{where}: DOCUMENT CHANGED — {w['file']} no longer matches the uploaded original")
    # oversized images slow the site down
    for img in (ROOT / "assets" / "img").rglob("*"):
        if img.is_file() and img.suffix.lower() != ".gif" and img.stat().st_size > MAX_IMAGE_KB * 1024:
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


def render_writing(data):
    """Non-technical writing samples: website only, never in the portfolio. Newest first; undated last."""
    out = []
    items = sorted(data.get("writing", []), key=lambda w: date_key(w) or (0, 0), reverse=True)
    for w in items:
        venue = " · ".join(esc(x) for x in (w["venue"], w.get("date")) if x)
        out.append(f"""      <div class="pub-item">
        <div class="pub-meta">
          <p class="pub-venue">{venue}</p>
          <h3 class="pub-title">{esc(w['title'])}</h3>
          <p class="writing-summary">{esc(w['summary'])}</p>
        </div>
        <a href="{href(w['file'])}" class="btn" target="_blank" rel="noopener">↓ PDF</a>
      </div>""")
    if not out:
        out.append('      <p class="empty-note">Coming soon.</p>')
    return "\n".join(out)


def render_in_prep(data):
    """Manuscripts in preparation: title, authors, status only (no summaries, by owner's request)."""
    owner = data.get("owner", "")
    out = []
    for m in data.get("in_preparation", []):
        authors = f'<p class="pub-authors">{bold_owner(m["authors"], owner)}</p>' if m.get("authors") else ""
        out.append(f"""      <div class="prep-item">
        <h3 class="pub-title">{esc(m['title'])}</h3>
        {authors}
        <p class="prep-status">{esc(m.get('status') or 'In preparation.')}</p>
      </div>""")
    return "\n".join(out)


def render_visuals(data):
    """Homepage 'In Motion' section: animations (GIFs), each linked to its project's portfolio entry."""
    ids = {p["id"]: p for p in data.get("projects", [])}
    out = []
    for v in data.get("visualizations", []):
        proj = ids.get(v.get("project"))
        link = ""
        if proj:
            target = f'portfolio.html#{esc(proj["id"])}' if (proj.get("portfolio") or {}).get("include") else f'#project-{esc(proj["id"])}'
            link = f'<a class="btn btn-sm" href="{target}">{esc(proj["title"])} →</a>'
        out.append(f"""      <figure class="viz-card">
        <img src="{href(v['src'])}" alt="{esc(v['caption'])}" loading="lazy" />
        <figcaption>
          <h3 class="project-title">{esc(v['title'])}</h3>
          <p class="project-desc">{esc(v['caption'])}</p>
          {link}
        </figcaption>
      </figure>""")
    return "\n".join(out)


def render_figure(f, n):
    cls = "pf-figure wide" if f.get("wide") else "pf-figure"
    cap = esc(f.get("caption", ""))
    return (f'<figure class="{cls}"><img src="{href(f["src"])}" alt="{cap}" loading="lazy" />'
            f'<figcaption><b>Fig. {n}.</b> {cap}</figcaption></figure>')


def portfolio_projects(data):
    """Projects in the portfolio, ordered by portfolio.rank (then newest first)."""
    items = [p for p in sorted_projects(data) if (p.get("portfolio") or {}).get("include")]
    return sorted(items, key=lambda p: (p["portfolio"].get("rank", 999)))


def render_portfolio_cover(data):
    items = portfolio_projects(data)
    nums = {p["id"]: f"{n:02d}" for n, p in enumerate(items, 1)}
    missing = portfolio_scene.scene_ids() - set(nums)
    if missing:
        err(f"portfolio cover scene points at projects not in the portfolio: {sorted(missing)}")
        return ""
    rows = "".join(f'<li><a href="#{esc(p["id"])}"><span class="pfc-cn">{n:02d}</span><span class="pfc-ct">{esc(p["title"])}</span>'
                   f'<span class="pfc-cm">{esc(p["tag"])} · {esc(p["date"])}</span></a></li>' for n, p in enumerate(items, 1))
    if data.get("current_research"):
        rows = ('<li><a href="#current-research"><span class="pfc-cn">Now</span><span class="pfc-ct">Current Research</span>'
                '<span class="pfc-cm">In preparation</span></a></li>') + rows
    legend = ('<div class="pfc-legend"><span><i class="lg-ch"></i>Chapter (click to jump; ordered by research focus)</span>'
              '<span><i class="lg-now"></i>In development (see Current Research)</span></div>')
    return (f'    <figure class="pfc-scene">{portfolio_scene.cover_svg(nums)}</figure>\n    {legend}\n'
            f'    <ol class="pfc-contents pfc-contents-mobile">{rows}</ol>')


ICONS = {
    "sound": '<path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M16 8.5a5 5 0 0 1 0 7"/><path d="M18.5 6a8.5 8.5 0 0 1 0 12"/>',
    "fish": '<path d="M3 12c3-5 9-5 13 0-4 5-10 5-13 0z"/><path d="M16 12l5-4v8z"/><circle cx="7.5" cy="11" r=".9" fill="currentColor"/>',
    "energy": '<rect x="3" y="7" width="16" height="10" rx="2"/><path d="M19 10h2v4h-2"/><path d="M11.5 8.5l-2.5 4h3l-1 3 3-4.5h-3z"/>',
    "air": '<path d="M3 8h11a3 3 0 1 0-3-3"/><path d="M3 12h15a3 3 0 1 1-3 3"/><path d="M3 16h8"/>',
}


def render_portfolio_current(data):
    """'Current Research': broad focus areas + manuscripts in preparation (no methods or results)."""
    cr = data.get("current_research") or {}
    if not cr:
        return ""
    owner = data.get("owner", "")
    cards = "".join(
        f'<div class="pf-area"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS.get(a.get("icon"), "")}</svg>'
        f'<h3>{esc(a["title"])}</h3><p>{esc(a["text"])}</p></div>' for a in cr.get("areas", []))
    preps = "".join(
        f'<div class="prep-item"><h4 class="pub-title">{esc(m["title"])}</h4>'
        + (f'<p class="pub-authors">{bold_owner(m["authors"], owner)}</p>' if m.get("authors") else "")
        + f'<p class="prep-status">{esc(m.get("status") or "In preparation.")}</p></div>'
        for m in data.get("in_preparation", []))
    return f"""  <section class="pf-chapter pf-now" id="current-research">
    <header class="pf-ch-head"><span class="pf-ch-num">Now</span><div><p class="pf-meta">In progress · 2026</p><h2 class="pf-title">Current Research</h2><div class="pf-ch-rule"></div><p class="pf-context">{esc(cr.get("intro", ""))}</p></div></header>
    <div class="pf-areas">{cards}</div>
    <h3 class="pf-subhead">Manuscripts in preparation</h3>
    <div class="prep-list">{preps}</div>
  </section>"""


def render_portfolio(data):
    owner = data.get("owner", "")
    site = data.get("site_url", "").rstrip("/")
    out = []
    for n, p in enumerate(portfolio_projects(data), 1):
        pf = p["portfolio"]
        meta = " · ".join(esc(x) for x in (p["tag"], p["date"]) if x)
        head = [f'<p class="pf-meta">{meta}</p>', f'<h2 class="pf-title">{esc(p["title"])}</h2>', '<div class="pf-ch-rule"></div>']
        if p.get("context"):
            head.append(f'<p class="pf-context">{esc(p["context"])}</p>')
        if p.get("team"):
            head.append(f'<p class="pf-team">{bold_owner(p["team"], owner)}</p>')
        if pf.get("role"):
            head.append(f'<p class="pf-role"><b>My role:</b> {esc(pf["role"])}</p>')
        th = portfolio_scene.thumb(p["id"])
        thumb_html = (f'<aside class="pf-ch-thumb">{th[0]}<p class="pf-thumb-k">{esc(th[1])}</p><p class="pf-thumb-t">{esc(th[2])}</p></aside>'
                      if th else "")
        parts = [f'    <header class="pf-ch-head{" has-thumb" if th else ""}"><span class="pf-ch-num">{n:02d}</span><div>{"".join(head)}</div>{thumb_html}</header>',
                 f'    <p class="pf-overview">{esc(pf["overview"])}</p>']
        docs = all_docs(p)
        if docs:
            links = "".join(f'<a class="btn" href="{href(site + "/" + d["file"])}" target="_blank" rel="noopener">'
                            f'↓ {esc(d.get("label") or "PDF")}</a>' for d in docs)
            parts.append(f'    <div class="pf-docs">{links}</div>')
        if pf.get("metrics"):
            tiles = "".join(f'<div class="pf-metric"><span class="pf-metric-value">{esc(m["value"])}</span>'
                            f'<span class="pf-metric-label">{esc(m["label"])}</span></div>' for m in pf["metrics"])
            parts.append(f'    <div class="pf-metrics" style="grid-template-columns: repeat({len(pf["metrics"])}, minmax(0, 1fr));">{tiles}</div>')
        figs = pf.get("figures", [])
        if figs:
            parts.append(f'    <div class="pf-figures lead">{render_figure(figs[0], 1)}</div>')
        if pf.get("results"):
            items = "".join(f"<li>{rich(r)}</li>" for r in pf["results"])
            heading = esc(pf.get("results_heading") or "Key results")
            parts.append(f'    <h3 class="pf-subhead">{heading}</h3>\n    <ol class="pf-results">{items}</ol>')
        for sec in pf.get("sections", []):
            parts.append(f'    <h3 class="pf-subhead">{esc(sec["heading"])}</h3>')
            for blk in sec.get("blocks", []):
                if "text" in blk:
                    parts.append(f'    <p class="pf-text">{rich(blk["text"])}</p>')
                elif "equation" in blk:
                    parts.append(f'    <div class="pf-eq"><img src="{href(blk["equation"])}" alt="{esc(blk.get("alt", "equation"))}" /></div>')
        if len(figs) > 1:
            rest = "".join(render_figure(f, i + 2) for i, f in enumerate(figs[1:]))
            parts.append(f'    <h3 class="pf-subhead">Figures</h3>\n    <div class="pf-figures">{rest}</div>')
        out.append(f'  <section class="pf-chapter" id="{esc(p["id"])}">\n' + "\n".join(parts) + "\n  </section>")
    if not out:
        out.append('  <section class="pf-chapter"><p class="empty-note">Portfolio entries coming soon.</p></section>')
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
    if (ROOT / "assets" / "portfolio.css").exists():
        h.update((ROOT / "assets" / "portfolio.css").read_bytes())
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
                    footer = ('<div style="width:100%;font:7.5px Helvetica,Arial,sans-serif;color:#8A9199;'
                              'padding:0 0.6in;display:flex;justify-content:space-between;">'
                              '<span>Jeffrey Kagle · Portfolio · jeffreykagle.com</span>'
                              '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
                    page.pdf(path=str(PDF), print_background=True, prefer_css_page_size=True,
                             display_header_footer=True, header_template="<div></div>", footer_template=footer)
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
    if "<!-- BUILD:updates -->" in idx:
        idx, _ = fill(idx, "updates", render_updates(data), "index.html")
    idx, _ = fill(idx, "projects", render_cards(data), "index.html")
    idx, _ = fill(idx, "publications", render_publications(data), "index.html")
    if "<!-- BUILD:visuals -->" in idx:
        idx, _ = fill(idx, "visuals", render_visuals(data), "index.html")
    idx, _ = fill(idx, "inprep", render_in_prep(data), "index.html")
    idx, _ = fill(idx, "writing", render_writing(data), "index.html")
    (ROOT / "index.html").write_text(idx)

    pf = (ROOT / "portfolio.html").read_text()
    pf, _ = fill(pf, "cover", render_portfolio_cover(data), "portfolio.html")
    pf, _ = fill(pf, "current", render_portfolio_current(data), "portfolio.html")
    pf, old_body = fill(pf, "portfolio", render_portfolio(data), "portfolio.html")
    new_body = re.search(r"<!-- BUILD:portfolio -->\n(.*?)<!-- /BUILD:portfolio -->", pf, re.S)
    changed = old_body is None or new_body is None or old_body != new_body.group(1)
    if changed or "pf-updated" not in pf:
        stamp = date.today().strftime("%B %Y")
        pf, _ = fill(pf, "updated", f'    <p class="pf-updated no-print">Last updated {stamp}</p>', "portfolio.html")
    (ROOT / "portfolio.html").write_text(pf)

    # cache-bust the stylesheet so browsers never pair a new page with an old cached stylesheet
    for pg in PAGES:
        t = t2 = (ROOT / pg).read_text()
        for css in ("style", "portfolio"):
            if (ROOT / "assets" / f"{css}.css").exists():
                ver = sha256(ROOT / "assets" / f"{css}.css")[:10]
                t2 = re.sub(rf'href="assets/{css}\.css(\?v=[0-9a-f]+)?"', f'href="assets/{css}.css?v={ver}"', t2)
        if t2 != t:
            (ROOT / pg).write_text(t2)

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
