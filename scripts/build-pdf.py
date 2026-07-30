#!/usr/bin/env python3
"""
build-pdf.py: regenerate shopify-seo-checklist.pdf from index.html.

index.html is the single source of truth. This script parses it, mirrors every
checklist item verbatim (label + description + links), renders a print-designed
HTML page with Double Your Ecommerce branding, and prints it to PDF with headless
Chrome. It exits non-zero if the PDF does not contain every item found in the
HTML, so the download can never silently drift from the live checklist again.

    python3 scripts/build-pdf.py

Dependencies
------------
Python:   3.9+ stdlib only (html.parser, subprocess, argparse). No pip installs.
Required: a Chromium-family browser for --print-to-pdf. Searched in this order:
            $CHROME_BIN
            /Applications/Helium.app/Contents/MacOS/Helium      (works headless)
            /Applications/Google Chrome.app/.../Google Chrome
            /Applications/Chromium.app/.../Chromium
            /Applications/Brave Browser.app/.../Brave Browser
            chromium / chromium-browser / google-chrome on $PATH
Optional: poppler (`brew install poppler`) for pdftotext / pdfinfo / pdftoppm.
            pdftotext  -> full text verification (the anti-drift check)
            pdfinfo    -> page count + page size report
            pdftoppm   -> `--png` page previews
          Without pdftotext the script still builds but warns that the strong
          verification was skipped; pass --require-verify to make that fatal.

Useful flags
------------
    --png              render page previews to build/preview-page-N.png
    --expect-items N   fail unless exactly N items were parsed (belt check)
    --require-verify   fail if pdftotext is unavailable
    --html-only        stop after writing the print HTML (design iteration)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = REPO / "index.html"
DEFAULT_PDF = REPO / "shopify-seo-checklist.pdf"
TEMPLATE = REPO / "scripts" / "pdf-template.html"
BUILD_DIR = REPO / "build"
PRINT_HTML = BUILD_DIR / "checklist-print.html"

CONSULT_URL = "https://savvycal.com/dye/initial-consult"
REPORT_URL = "https://doubleyourecommerce.com/services/seo-for-growing-stores/"
SITE_URL = "https://doubleyourecommerce.com"

INLINE_OK = {"a", "em", "strong", "b", "i", "br", "code", "u", "sup", "sub"}
VOID = {"br"}

CHROME_CANDIDATES = [
    "/Applications/Helium.app/Contents/MacOS/Helium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def die(msg: str):
    print(f"\n  FAIL  {msg}\n", file=sys.stderr)
    sys.exit(1)


def note(msg: str) -> None:
    print(f"  {msg}")


# --------------------------------------------------------------------------- #
# parsing index.html
# --------------------------------------------------------------------------- #


class ChecklistParser(HTMLParser):
    """Pulls the hero copy and every checklist section/item out of index.html.

    Captures inline markup (links, <em>) verbatim so the PDF mirrors the site
    instead of paraphrasing it.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hero: dict = {}
        self.sections: list = []
        self.cur = None
        self.item = None
        self.div_depth = 0
        self.section_depth = -1
        self.item_depth = -1
        self.cap = None

    # -- capture helpers ---------------------------------------------------- #

    def _start_cap(self, tag: str, dest: dict, key: str) -> None:
        self.cap = {"tag": tag, "depth": 0, "parts": [], "links": [], "dest": dest, "key": key}

    def _finish_cap(self) -> None:
        cap = self.cap
        self.cap = None
        if cap is None:
            return
        text = "".join(cap["parts"])
        text = re.sub(r"\s+", " ", text).strip()
        cap["dest"][cap["key"]] = text
        cap["dest"][cap["key"] + "_links"] = cap["links"]

    # -- HTMLParser hooks --------------------------------------------------- #

    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = {k: (v or "") for k, v in attrs_list}
        classes = attrs.get("class", "").split()

        if self.cap is not None:
            if tag == self.cap["tag"]:
                self.cap["depth"] += 1
            if tag in INLINE_OK:
                if tag == "a":
                    href = attrs.get("href", "").strip()
                    if href.startswith(("http://", "https://")):
                        self.cap["links"].append(href)
                        self.cap["parts"].append(f'<a href="{html.escape(href, quote=True)}">')
                    else:
                        self.cap["parts"].append("<span>")  # keep text, drop dead link
                else:
                    self.cap["parts"].append(f"<{tag}>")
            return

        if tag == "div":
            self.div_depth += 1
            if "section" in classes and self.cur is None:
                self.cur = {"badge": "", "h2": "", "dek": "", "dek_links": [], "items": []}
                self.section_depth = self.div_depth
            elif "checklist-item" in classes and self.cur is not None and self.item is None:
                self.item = {"label": "", "label_links": [], "desc": "", "desc_links": []}
                self.item_depth = self.div_depth
            return

        if self.cur is not None:
            if tag == "span" and "section-badge" in classes and not self.cur["badge"]:
                self._start_cap("span", self.cur, "badge")
            elif tag == "h2" and not self.cur["h2"]:
                self._start_cap("h2", self.cur, "h2")
            elif tag == "p" and "section-description" in classes and not self.cur["dek"]:
                self._start_cap("p", self.cur, "dek")
        if self.item is not None:
            if tag == "label" and not self.item["label"]:
                self._start_cap("label", self.item, "label")
            elif tag == "p" and "item-description" in classes and not self.item["desc"]:
                self._start_cap("p", self.item, "desc")
        if self.cur is None:
            if tag == "span" and classes == ["badge"] and "kicker" not in self.hero:
                self._start_cap("span", self.hero, "kicker")
            elif tag == "h1" and "title" not in self.hero:
                self._start_cap("h1", self.hero, "title")
            elif tag == "p" and "hero-subtitle" in classes and "dek" not in self.hero:
                self._start_cap("p", self.hero, "dek")

    def handle_startendtag(self, tag, attrs) -> None:
        if self.cap is not None and tag in VOID:
            self.cap["parts"].append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if self.cap is not None:
            if tag == self.cap["tag"]:
                if self.cap["depth"] == 0:
                    self._finish_cap()
                    return
                self.cap["depth"] -= 1
            if tag in INLINE_OK and tag not in VOID:
                self.cap["parts"].append(f"</{tag}>")
            return

        if tag == "div":
            if self.item is not None and self.div_depth == self.item_depth:
                if self.item["label"]:
                    self.cur["items"].append(self.item)
                self.item = None
                self.item_depth = -1
            if self.cur is not None and self.div_depth == self.section_depth:
                if self.cur["items"]:
                    self.sections.append(self.cur)
                self.cur = None
                self.section_depth = -1
            self.div_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.cap is not None:
            self.cap["parts"].append(html.escape(data, quote=False))


def close_open_spans(fragment: str) -> str:
    """Balance the <span> stand-ins we emit in place of non-http anchors."""
    opens = fragment.count("<span>")
    closes = fragment.count("</span>")
    return fragment + "</span>" * max(0, opens - closes)


# --------------------------------------------------------------------------- #
# link presentation
# --------------------------------------------------------------------------- #


def is_dye(href: str) -> bool:
    return "doubleyourecommerce.com" in href


def is_deep(href: str) -> bool:
    tail = re.sub(r"^https?://[^/]+", "", href)
    return len(tail.strip("/")) > 0


def order_links(hrefs: list) -> list:
    """DYE deep links first (the money links), then other DYE, then the rest."""
    seen = set()
    uniq = []
    for h in hrefs:
        norm = h.rstrip("/")
        if norm in seen:
            continue
        seen.add(norm)
        uniq.append(h)

    def rank(h: str) -> int:
        if is_dye(h) and is_deep(h):
            return 0
        if is_dye(h):
            return 1
        return 2

    return sorted(uniq, key=rank)


def short_url(href: str, limit: int = 54) -> str:
    s = re.sub(r"^https?://", "", href)
    s = re.sub(r"^www\.", "", s)
    if s.endswith("/") and s.count("/") > 1:
        s = s[:-1]
    if len(s) <= limit:
        return s
    host, _, path = s.partition("/")
    tail = path.split("/")[-1] or path
    squeezed = f"{host}/…/{tail}"
    return squeezed if len(squeezed) <= limit else squeezed[: limit - 1] + "…"


def links_line(hrefs: list, label: str = "Links") -> str:
    hrefs = order_links(hrefs)
    if not hrefs:
        return ""
    parts = []
    for h in hrefs:
        parts.append(f'<a href="{html.escape(h, quote=True)}">{html.escape(short_url(h, 72))}</a>')
    joined = '<span class="sep">·</span>'.join(parts)
    return f'<p class="links"><span class="lk-label">{label}</span>{joined}</p>'


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #


def attr(text: str) -> str:
    """Captured fragments are already HTML-escaped; make one attribute-safe."""
    return re.sub(r"<[^>]+>", "", text).replace('"', "&quot;")


def first_sentence(text: str) -> str:
    flat = re.sub(r"<[^>]+>", "", text)
    flat = re.sub(r"\s+", " ", flat).strip()
    m = re.match(r"^(.+?[.!?])(\s|$)", flat)
    return (m.group(1) if m else flat).strip()


def render_flow(hero: dict, sections: list, today: str) -> str:
    total_items = sum(len(s["items"]) for s in sections)
    blocks = []

    toc = []
    for s in sections:
        n = len(s["items"])
        toc.append(
            '<div class="toc-row"><span class="t">'
            f'{s["badge"]}</span>'
            f'<span class="n">{n} item{"s" if n != 1 else ""}</span></div>'
        )

    dek = first_sentence(hero.get("dek", ""))
    blocks.append(
        f"""<section class="blk cover" data-break="page" data-nofoot="1">
  <span class="kicker">{hero.get('kicker', 'Shopify SEO Checklist')}</span>
  <h1>{hero.get('title', 'Shopify SEO Checklist')}</h1>
  <div class="amber-rule"></div>
  <p class="dek">{dek}</p>
  <div class="byline">
    from <span class="who">Double Your Ecommerce</span><br>
    Kai Davis, your Shopify SEO guy<br>
    <span class="url">doubleyourecommerce.com</span>
  </div>
  <div class="spacer"></div>
  <div class="toc">
    <p class="toc-title">What is inside</p>
    {''.join(toc)}
  </div>
  <p class="meta">{total_items} items across {len(sections)} sections &nbsp;·&nbsp; generated {today} &nbsp;·&nbsp; always current at shopifyseochecklist.net</p>
  <div class="spacer-b"></div>
</section>"""
    )

    for s in sections:
        n = len(s["items"])
        sec = attr(s["badge"])
        dek_html = close_open_spans(s["dek"])
        blocks.append(
            f"""<div class="blk sec-head" data-break="page" data-sec="{sec}">
  <span class="badge">{s['badge']}</span>
  <h2>{s['h2']}</h2>
  <p class="sec-dek">{dek_html}</p>
  {links_line(s.get('dek_links', []), 'Guides')}
  <p class="count">{n} item{'s' if n != 1 else ''}</p>
</div>"""
        )
        for it in s["items"]:
            desc = close_open_spans(it["desc"])
            hrefs = list(it.get("desc_links", [])) + list(it.get("label_links", []))
            blocks.append(
                f"""<div class="blk item" data-sec="{sec}">
  <span class="cbx"></span>
  <div>
    <p class="label">{close_open_spans(it['label'])}</p>
    {f'<p class="desc">{desc}</p>' if desc else ''}
    {links_line(hrefs)}
  </div>
</div>"""
            )

    blocks.append(
        f"""<section class="blk cta" data-break="page">
  <span class="badge">Next step</span>
  <h2>Want a second pair of eyes on your store?</h2>
  <div class="amber-rule"></div>
  <p class="dek">If you’d like someone to give you personalized advice about what will move
  the needle for <em>your</em> store first, here are two ways to do that.</p>

  <div class="offer">
    <h3>Book a free consultation</h3>
    <p>We’ll have a call so I can learn more about you, your store, your customers, and your
    goals with SEO. I’ll share my recommendations for how I can help.</p>
    <a class="go" href="{CONSULT_URL}">{short_url(CONSULT_URL, 70)}</a>
  </div>

  <div class="offer">
    <h3>Get an SEO Opportunity Report</h3>
    <p>A prioritized report on what to do to grow your store.</p>
    <a class="go" href="{REPORT_URL}">{short_url(REPORT_URL, 70)}</a>
  </div>

</section>"""
    )

    return "\n".join(blocks)


def render_print_html(index_path: Path, today: str):
    raw = index_path.read_text(encoding="utf-8")
    parser = ChecklistParser()
    parser.feed(raw)
    parser.close()

    sections = parser.sections
    parsed_items = sum(len(s["items"]) for s in sections)
    raw_items = len(re.findall(r'class="checklist-item"', raw))
    raw_sections = len(re.findall(r'<div class="section"(?:\s|>)', raw))

    note(f"parsed {len(sections)} sections, {parsed_items} items from {index_path.name}")
    if parsed_items != raw_items:
        die(
            f"item drift while parsing: index.html has {raw_items} "
            f'occurrences of class="checklist-item" but the parser produced {parsed_items}. '
            "The markup shape changed; fix the parser before shipping a PDF."
        )
    if len(sections) != raw_sections:
        die(
            f'section drift while parsing: {raw_sections} <div class="section"> in index.html, '
            f"{len(sections)} parsed."
        )
    for s in sections:
        if not s["badge"] or not s["h2"]:
            die(f"section missing badge or heading: {s.get('badge')!r} / {s.get('h2')!r}")
        for it in s["items"]:
            if not it["label"]:
                die(f'item with no label in section "{s["badge"]}"')

    template = TEMPLATE.read_text(encoding="utf-8")
    flow = render_flow(parser.hero, sections, today)
    title = f"Shopify SEO Checklist ({parsed_items} Items) · Double Your Ecommerce"
    out = template.replace("{{TITLE}}", html.escape(title)).replace("{{FLOW}}", flow)
    return out, parser.hero, sections


# --------------------------------------------------------------------------- #
# chrome
# --------------------------------------------------------------------------- #


def find_chrome(explicit) -> str:
    if explicit:
        if not Path(explicit).exists():
            die(f"--chrome {explicit} does not exist")
        return explicit
    env = os.environ.get("CHROME_BIN")
    if env and Path(env).exists():
        return env
    for cand in CHROME_CANDIDATES:
        if Path(cand).exists():
            return cand
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    die(
        "no Chromium-family browser found for --print-to-pdf. Install Chromium or set "
        "CHROME_BIN=/path/to/browser (Helium at /Applications/Helium.app works)."
    )


def run_headless(chrome: str, url: str, watch: Path, extra: list, timeout: float = 120.0) -> None:
    """Run headless Chrome and stop it as soon as `watch` is written and stable.

    Helium (and some Chrome builds) do not exit after --print-to-pdf, so waiting
    on the process is not an option: poll the artifact instead.
    """
    if watch.exists():
        watch.unlink()
    profile = tempfile.mkdtemp(prefix="pdfgen-profile-")
    cmd = [
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--hide-scrollbars",
        "--virtual-time-budget=5000",
        f"--user-data-dir={profile}",
        *extra,
        url,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    deadline = time.time() + timeout
    stable = 0
    last = -1
    try:
        while time.time() < deadline:
            if watch.exists():
                size = watch.stat().st_size
                if size > 1024 and size == last:
                    stable += 1
                    if stable >= 3:
                        return
                else:
                    stable = 0
                last = size
            elif proc.poll() is not None:
                err = (proc.stderr.read() or b"").decode("utf-8", "replace")[-800:]
                die(f"headless browser exited without writing {watch.name}\n{err}")
            time.sleep(0.35)
        die(f"timed out after {timeout:.0f}s waiting for {watch.name}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


# --------------------------------------------------------------------------- #
# verification
# --------------------------------------------------------------------------- #


def normalize(text: str) -> str:
    t = text.replace("’", "'").replace("‘", "'")
    t = t.replace("“", '"').replace("”", '"')
    t = t.replace("—", "-").replace("–", "-").replace("…", "...")
    t = t.replace(" ", " ")
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def pdf_page_count(pdf: Path) -> int:
    if shutil.which("pdfinfo"):
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
        m = re.search(r"^Pages:\s+(\d+)", out, re.M)
        if m:
            return int(m.group(1))
    blob = pdf.read_bytes()
    return len(re.findall(rb"/Type\s*/Page[^s]", blob))


def verify(pdf: Path, sections: list, require: bool):
    pages = pdf_page_count(pdf)
    if pages < len(sections) + 2:
        die(f"PDF has only {pages} pages, expected at least {len(sections) + 2}")

    if not shutil.which("pdftotext"):
        msg = "pdftotext not found: skipped the item-by-item PDF verification"
        if require:
            die(msg + " (--require-verify)")
        note("WARN  " + msg + " (brew install poppler)")
        return pages, ""

    text = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(pdf), "-"], capture_output=True, text=True
    ).stdout
    hay = normalize(text)

    if "pdf layout overflow" in hay:
        die("the paginator flagged a block taller than one page (PDF-LAYOUT-OVERFLOW in the PDF)")

    missing = []
    for s in sections:
        if normalize(s["badge"]) not in hay:
            missing.append(f'section badge: {s["badge"]}')
        for it in s["items"]:
            needle = normalize(it["label"])[:60]
            if needle and needle not in hay:
                missing.append("item: " + re.sub(r"<[^>]+>", "", it["label"])[:70])

    total = sum(len(s["items"]) for s in sections)
    if missing:
        print(
            f"\n  FAIL  {len(missing)} item(s)/section(s) from index.html are NOT in the PDF:",
            file=sys.stderr,
        )
        for m in missing[:20]:
            print(f"        - {m}", file=sys.stderr)
        die("PDF does not mirror index.html. Do not ship this file.")
    note(f"verified all {total} item labels + {len(sections)} section headings are in the PDF")
    return pages, text


def render_pngs(pdf: Path, pages: list) -> list:
    out = []
    if not shutil.which("pdftoppm"):
        note("WARN  pdftoppm not found, skipping PNG previews (brew install poppler)")
        return out
    for stale in BUILD_DIR.glob("preview-page-*.png"):
        stale.unlink()
    for p in pages:
        stem = BUILD_DIR / f"preview-page-{p}"
        # -singlefile keeps the exact filename: without it pdftoppm appends a
        # page-number suffix whose width tracks the page count, which is how a
        # stale preview once got mistaken for a fresh one.
        subprocess.run(
            [
                "pdftoppm", "-png", "-r", "110", "-singlefile",
                "-f", str(p), "-l", str(p), str(pdf), str(stem),
            ],
            check=True,
        )
        final = Path(f"{stem}.png")
        if final.exists():
            out.append(final)
    return out


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description="Build shopify-seo-checklist.pdf from index.html")
    ap.add_argument("--index", default=str(DEFAULT_INDEX))
    ap.add_argument("--out", default=str(DEFAULT_PDF))
    ap.add_argument("--chrome", default=None, help="path to a Chromium-family binary")
    ap.add_argument("--expect-items", type=int, default=None)
    ap.add_argument("--require-verify", action="store_true")
    ap.add_argument("--html-only", action="store_true")
    ap.add_argument("--png", action="store_true", help="render page previews as PNG")
    ap.add_argument("--png-pages", default="", help="comma-separated page numbers for --png")
    args = ap.parse_args()

    index_path = Path(args.index).resolve()
    pdf_path = Path(args.out).resolve()
    if not index_path.exists():
        die(f"{index_path} not found")
    if not TEMPLATE.exists():
        die(f"{TEMPLATE} not found")

    today = _dt.date.today().strftime("%B %d, %Y").replace(" 0", " ")
    print("\nbuild-pdf.py")
    html_out, hero, sections = render_print_html(index_path, today)

    total_items = sum(len(s["items"]) for s in sections)
    if args.expect_items is not None and total_items != args.expect_items:
        die(f"--expect-items {args.expect_items} but index.html yielded {total_items}")

    BUILD_DIR.mkdir(exist_ok=True)
    PRINT_HTML.write_text(html_out, encoding="utf-8")
    note(f"wrote build/{PRINT_HTML.name} ({len(html_out) / 1024:.0f} KB)")
    if args.html_only:
        return 0

    chrome = find_chrome(args.chrome)
    note(f"printing with {chrome}")
    run_headless(
        chrome,
        PRINT_HTML.as_uri(),
        pdf_path,
        [f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer"],
    )
    size_kb = pdf_path.stat().st_size / 1024
    note(f"wrote {pdf_path.name} ({size_kb:.0f} KB)")

    pages, _text = verify(pdf_path, sections, args.require_verify)

    if args.png:
        wanted = (
            [int(x) for x in args.png_pages.split(",") if x.strip()]
            if args.png_pages
            else [1, 2, pages]
        )
        for p in render_pngs(pdf_path, sorted(set(wanted))):
            note(f"preview build/{p.name}")

    print(
        f"\n  OK    {total_items} items · {len(sections)} sections · {pages} pages · "
        f"{size_kb:.0f} KB -> {pdf_path.name}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
