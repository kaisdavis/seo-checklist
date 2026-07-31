# shopifyseochecklist.net

Static site for the Shopify SEO Checklist, a free lead magnet from
[Double Your Ecommerce](https://doubleyourecommerce.com). Plain HTML, CSS, and JS,
no build step for the site itself.

`index.html` is the single source of truth for checklist content. The downloadable
PDF is generated from it, never hand-edited.

## Regenerating the PDF

`shopify-seo-checklist.pdf` (linked from `thank-you.html` and from the Bento email
flow) is built from `index.html` by one command:

```
python3 scripts/build-pdf.py
```

That parses every section and item out of `index.html`, renders
`build/checklist-print.html` from `scripts/pdf-template.html`, prints it to PDF with
headless Chrome, then verifies the result. Run it any time checklist copy changes,
then commit the regenerated PDF.

**What it needs:** Python 3.9+ (stdlib only, no pip installs) and a Chromium-family
browser. It looks for `$CHROME_BIN`, then Helium, Chrome, Chromium, Brave, and Edge,
then `chromium` / `google-chrome` on `$PATH`. Poppler (`brew install poppler`) is
optional but recommended: `pdftotext` powers the verification step, `pdfinfo` reports
the page count, `pdftoppm` renders previews.

**Anti-drift teeth.** The script exits non-zero, and says why, when:

- the parsed item count does not match the number of `class="checklist-item"`
  occurrences in `index.html` (the markup shape changed, so fix the parser),
- the parsed section count does not match the number of `<div class="section">` blocks,
- any item label or section heading is missing from the finished PDF text layer,
- the paginator had to overflow a block taller than one page,
- `--expect-items N` is passed and the count differs.

A non-zero exit means do not ship that PDF. The invariant these checks enforce: the
PDF contains every section and every item in `index.html`, exactly once.

**Handy flags**

| Flag | Effect |
| --- | --- |
| `--png` | render page previews to `build/preview-page-N.png` |
| `--png-pages 1,3,9` | choose which pages to preview |
| `--html-only` | stop after writing the print HTML, for design iteration |
| `--expect-items 35` | fail unless exactly 35 items were parsed |
| `--require-verify` | fail instead of warn when `pdftotext` is missing |
| `--chrome /path/to/browser` | pick the browser explicitly |
| `--out other.pdf` | write somewhere other than the repo root PDF |

Design lives in `scripts/pdf-template.html`: DYE palette (green `#157a50`, amber
`#fcd34d`, slate neutrals), system sans for headings and labels, Georgia for reading
copy, and a small JS paginator that flows content into fixed-height pages so every
page can carry a real footer with a page number. Content is never written there; it
all comes from `index.html`.

## Layout

| Path | What it is |
| --- | --- |
| `index.html` | the checklist itself, source of truth for all item copy |
| `styles.css`, `script.js`, `tracking.js` | site styles and behavior; styles.css carries the DYE design tokens (same palette as the PDF) with the webfonts embedded as data URIs |
| `fonts/` | canonical woff2 binaries (Bricolage Grotesque 800, Atkinson Hyperlegible 400/700); the served copies live base64-inlined in styles.css |
| `pdf-preview-860.webp/.jpg` | hero image, a render of PDF page 1; regenerate via `build-pdf.py --png --png-pages 1` after cover changes |
| `thank-you.html` | post-signup page, links to the PDF |
| `simple-checklist.html`, `privacy.html`, `terms.html`, `404.html` | supporting pages |
| `scripts/build-pdf.py` | the PDF generator |
| `scripts/pdf-template.html` | print design and paginator |
| `shopify-seo-checklist.pdf` | generated artifact, committed, do not hand-edit |
| `build/` | intermediate print HTML and PNG previews, git-ignored |
