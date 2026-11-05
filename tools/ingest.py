#!/usr/bin/env python3
"""Bring a new project document into the site without modifying it.

  python3 tools/ingest.py doc <file> <slug>
      Stores the document as assets/docs/<slug>.pdf (PDFs are copied byte-for-byte;
      .docx/.pptx/etc. are converted to PDF, the original upload is untouched),
      records its sha256, pulls candidate figures out of it into /tmp/ingest/<slug>/
      (NOT the repo), makes page contact sheets for picking figures, and prints a
      data/site.json stub.

  python3 tools/ingest.py crop <slug> <page> <x0> <y0> <x1> <y1> <name> [--png] [--dpi 200]
      Renders a region of a page of assets/docs/<slug>.pdf (coords are fractions 0-1
      of page width/height, origin top-left) to assets/img/<slug>/<name>.jpg|png.
      Use for vector plots/diagrams that pdfimages can't extract.

  python3 tools/ingest.py image <src> <slug> <name> [--png] [--max 1600]
      Resizes + compresses an image (extracted figure or a photo the owner sent)
      into assets/img/<slug>/<name>.jpg|png.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parent.parent
WORK = Path("/tmp/ingest")
MIN_SIDE = 250  # ignore logos/icons smaller than this


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save_image(im, slug, name, png=False, max_side=1600):
    im = ImageOps.exif_transpose(im)
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    out_dir = ROOT / "assets" / "img" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    if png:
        out = out_dir / f"{name}.png"
        im.save(out, optimize=True)
    else:
        out = out_dir / f"{name}.jpg"
        if im.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", im.size, "white")
            im = im.convert("RGBA")
            bg.paste(im, mask=im.split()[-1])
            im = bg
        im.convert("RGB").save(out, quality=84, optimize=True, progressive=True)
    print(f"saved {out.relative_to(ROOT)}  {im.size[0]}x{im.size[1]}  {out.stat().st_size // 1024} KB")
    return out


def contact_sheets(pdf, out_dir, per_sheet=24, cols=6):
    pages = out_dir / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pdftoppm", "-r", "36", "-png", str(pdf), str(pages / "p")], check=True)
    files = sorted(pages.glob("p-*.png"), key=lambda f: int(f.stem.split("-")[-1]))
    sheets = []
    for s in range(0, len(files), per_sheet):
        chunk = files[s:s + per_sheet]
        ims = [Image.open(f).convert("RGB") for f in chunk]
        w = max(i.width for i in ims); h = max(i.height for i in ims) + 16
        rows = (len(ims) + cols - 1) // cols
        sheet = Image.new("RGB", (w * cols, h * rows), "white")
        d = ImageDraw.Draw(sheet)
        for k, (f, im) in enumerate(zip(chunk, ims)):
            x, y = (k % cols) * w, (k // cols) * h
            sheet.paste(im, (x, y + 16))
            d.rectangle([x, y + 16, x + im.width - 1, y + 16 + im.height - 1], outline="#cccccc")
            d.text((x + 4, y + 2), f"p{int(f.stem.split('-')[-1])}", fill="#c00000")
        path = out_dir / f"sheet-{s // per_sheet + 1}.png"
        sheet.save(path)
        sheets.append(path)
    return sheets


def extract_images(pdf, out_dir):
    raw = out_dir / "embedded"
    raw.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pdfimages", "-png", "-p", str(pdf), str(raw / "img")], check=True)
    seen, keep = set(), []
    for f in sorted(raw.glob("*.png")):
        try:
            im = Image.open(f)
            w, h = im.size
        except Exception:
            continue
        digest = hashlib.md5(f.read_bytes()).hexdigest()
        if w < MIN_SIDE or h < MIN_SIDE or digest in seen:
            f.unlink()
            continue
        seen.add(digest)
        page = int(f.stem.split("-")[1])
        keep.append({"page": page, "size": f"{w}x{h}", "path": str(f)})
    return keep


def cmd_doc(args):
    src = Path(args.file)
    if not src.is_file():
        sys.exit(f"no such file: {src}")
    dest = ROOT / "assets" / "docs" / f"{args.slug}.pdf"
    if dest.exists() and not args.force:
        sys.exit(f"{dest.relative_to(ROOT)} already exists — use a new slug, or --force to replace")
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_hash = sha256(src)
    if src.suffix.lower() == ".pdf":
        shutil.copyfile(src, dest)
        if sha256(dest) != src_hash:
            sys.exit("copy verification failed")
        note = "copied byte-for-byte"
    else:
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", tmp, str(src)],
                               capture_output=True, text=True, timeout=300)
            out = list(Path(tmp).glob("*.pdf"))
            if not out:
                sys.exit(f"conversion to PDF failed:\n{r.stderr}")
            shutil.copyfile(out[0], dest)
        if sha256(src) != src_hash:
            sys.exit("the original upload changed during conversion — aborting")
        note = f"converted from {src.suffix} to PDF (original upload untouched)"
    doc_hash = sha256(dest)

    work = WORK / args.slug
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    pages = subprocess.run(["pdfinfo", str(dest)], capture_output=True, text=True).stdout
    n_pages = next((l.split()[-1] for l in pages.splitlines() if l.startswith("Pages:")), "?")
    figs = extract_images(dest, work)
    sheets = contact_sheets(dest, work)

    print(f"document: {dest.relative_to(ROOT)}  ({note}, {n_pages} pages, {dest.stat().st_size // 1024} KB)")
    print(f"sha256:   {doc_hash}")
    print(f"\ncontact sheets (pick figures from these):")
    for s in sheets:
        print(f"  {s}")
    print(f"\nembedded images >= {MIN_SIDE}px ({len(figs)}):")
    for f in figs:
        print(f"  p{f['page']:<4} {f['size']:<11} {f['path']}")
    stub = {
        "id": args.slug, "title": "", "tag": "", "date": "", "context": "", "team": "",
        "summary": "",
        "cover": f"assets/img/{args.slug}/cover.jpg", "cover_alt": "",
        "document": {"label": "", "file": str(dest.relative_to(ROOT)), "sha256": doc_hash},
        "portfolio": {"include": False, "overview": "", "metrics": [], "results": [], "figures": []},
    }
    print("\nsite.json stub (add to the TOP of \"projects\"):")
    print(json.dumps(stub, indent=2, ensure_ascii=False))


def cmd_crop(args):
    pdf = ROOT / "assets" / "docs" / f"{args.slug}.pdf"
    if not pdf.exists():
        sys.exit(f"no document for slug {args.slug}: {pdf}")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", str(args.dpi), "-png", "-f", str(args.page), "-l", str(args.page),
                        str(pdf), f"{tmp}/p"], check=True)
        page = Image.open(next(Path(tmp).glob("p*.png"))).convert("RGB")
        W, H = page.size
        box = (int(args.x0 * W), int(args.y0 * H), int(args.x1 * W), int(args.y1 * H))
        save_image(page.crop(box), args.slug, args.name, png=args.png)


def cmd_image(args):
    save_image(Image.open(args.src), args.slug, args.name, png=args.png, max_side=args.max)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("doc"); d.add_argument("file"); d.add_argument("slug"); d.add_argument("--force", action="store_true")
    c = sub.add_parser("crop"); c.add_argument("slug"); c.add_argument("page", type=int)
    for k in ("x0", "y0", "x1", "y1"):
        c.add_argument(k, type=float)
    c.add_argument("name"); c.add_argument("--png", action="store_true"); c.add_argument("--dpi", type=int, default=200)
    i = sub.add_parser("image"); i.add_argument("src"); i.add_argument("slug"); i.add_argument("name")
    i.add_argument("--png", action="store_true"); i.add_argument("--max", type=int, default=1600)
    args = ap.parse_args()
    {"doc": cmd_doc, "crop": cmd_crop, "image": cmd_image}[args.cmd](args)


if __name__ == "__main__":
    main()
