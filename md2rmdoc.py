#!/usr/bin/env python3
"""Convert Markdown to a reMarkable .rmdoc (PDF payload, annotatable on-device).

    ./md2rmdoc.py notes.md                  -> notes.rmdoc
    ./md2rmdoc.py notes.md -n "My Notes" -o out.rmdoc
    ./md2rmdoc.py notes.md -- --toc -V mainfont=Palatino      # extra pandoc args,
                                                             # overriding any default

Needs pandoc + a LaTeX engine (xelatex). Copy the .rmdoc to the tablet via the
USB web UI (http://10.11.99.1) or the reMarkable app.
"""
import argparse, json, re, subprocess, sys, tempfile, zlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

# ponytail: Paper Pro is 1620x2160 px @ 229 dpi. Calibration knob: if pages
# letterbox or crop on your firmware, change --paper / --margin.
PAPER = "179.7mm", "239.6mm"
# Wide right margin is a gutter to write in. ~71 chars/line at 12pt.
MARGIN = "left=14mm,right=30mm,top=14mm,bottom=16mm"
# Charter ships with macOS and was drawn for low-resolution screens, so it
# holds up on e-ink where Latin Modern goes thin.
STYLE = {"mainfont": "Charter", "monofont": "Menlo", "sansfont": "Avenir Next",
         "linestretch": "1.15", "colorlinks": "true",
         "linkcolor": "NavyBlue", "urlcolor": "NavyBlue"}


def page_count(pdf: bytes) -> int:
    """Count /Type /Page objects, including those inside compressed object streams."""
    blobs = [pdf]
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        try:
            blobs.append(zlib.decompress(m.group(1)))
        except zlib.error:
            pass
    return sum(len(re.findall(rb"/Type\s*/Page[^s]", b)) for b in blobs)


def have_tex(pkg: str) -> bool:
    return subprocess.run(["kpsewhich", f"{pkg}.sty"], capture_output=True).returncode == 0


def preamble() -> list:
    """Keep long URLs, inline code and code lines from running off the page.

    pandoc puts header-includes near the top of the preamble, so PassOptionsToPackage
    still reaches the url package that hyperref pulls in later.
    """
    tex = [r"\PassOptionsToPackage{hyphens}{url}", r"\emergencystretch=3em",
           # pandoc escapes _ as the macro \_, which blocks hyphenation of the
           # whole word: snake_case in prose runs off the page without this.
           r"\renewcommand{\_}{\textunderscore\allowbreak}",
           # Let long /paths/like/this and dotted.name.chains break (xelatex only).
           # Digits get their own class so version numbers like 3.14 never split.
           r"\ifdefined\XeTeXinterchartokenstate"
           r"\XeTeXinterchartokenstate=1"
           r"\newXeTeXintercharclass\breakafter"
           r"\newXeTeXintercharclass\digitclass"
           r"\XeTeXcharclass`\/=\breakafter"
           r"\XeTeXcharclass`\.=\breakafter"
           r"\count255=48 \loop \XeTeXcharclass\count255=\digitclass"
           r" \advance\count255 by1 \ifnum\count255<58 \repeat"
           r"\XeTeXinterchartoks\breakafter 0={\allowbreak}"
           r"\fi"]
    if have_tex("fvextra"):   # wrap long lines inside fenced code blocks
        tex += [r"\usepackage{fvextra}", r"\fvset{breaklines=true,breakanywhere=true}",
                # Fences with no language become plain LaTeX verbatim, which fvextra
                # does not touch; swap it for a breakable fancyvrb Verbatim.
                r"\RecustomVerbatimEnvironment{verbatim}{Verbatim}"
                r"{breaklines=true,breakanywhere=true}"]
    if have_tex("hyphenat"):  # let long `inline_code_tokens` break
        tex.append(r"\usepackage[htt]{hyphenat}")
    return [x for t in tex for x in ("-V", f"header-includes={t}")]


def style_args(font_size: str, extra: list) -> list:
    """STYLE defaults as -V args, minus keys set in extra (pandoc concatenates duplicates)."""
    set_by_user = {a.split("=")[0] for flag, a in zip(extra, extra[1:])
                   if flag in ("-V", "--variable")}
    style = {"fontsize": font_size, **STYLE}
    return [x for k, v in style.items() if k not in set_by_user for x in ("-V", f"{k}={v}")]


def md_to_pdf(md: Path, paper, margin, font_size, engine, extra) -> bytes:
    out = Path(tempfile.mkdtemp()) / "out.pdf"
    subprocess.run(
        ["pandoc", str(md), "-o", str(out), f"--pdf-engine={engine}",
         # geometry repeats as a comma list, so a user --  -V geometry:... wins.
         "-V", f"geometry:paperwidth={paper[0]}",
         "-V", f"geometry:paperheight={paper[1]}",
         "-V", f"geometry:{margin}",
         *style_args(font_size, extra), *preamble(), *extra],
        check=True,
    )
    return out.read_bytes()


def write_rmdoc(pdf: bytes, name: str, dest: Path) -> None:
    doc = str(uuid4())
    now = str(int(datetime.now().timestamp() * 1000))
    pages = page_count(pdf)
    with ZipFile(dest, "w", ZIP_DEFLATED) as z:
        z.writestr(f"{doc}.pdf", pdf)
        z.writestr(f"{doc}.metadata", json.dumps({
            "createdTime": now, "lastModified": now, "lastOpened": now,
            "lastOpenedPage": 0, "parent": "", "pinned": False,
            "type": "DocumentType", "visibleName": name,
        }))
        z.writestr(f"{doc}.content", json.dumps({
            "coverPageNumber": 0,
            "documentMetadata": {},
            "dummyDocument": False,
            "extraMetadata": {},
            "fileType": "pdf",
            "fontName": "",
            "formatVersion": 2,
            "lineHeight": -1,
            "margins": 125,
            "orientation": "portrait",
            # xochitl derives the page list from the PDF itself; listing pages
            # here (as notebooks do) makes it append them on top -> doubled doc.
            "originalPageCount": pages,
            "pageCount": pages,
            "pageTags": [],
            "sizeInBytes": str(len(pdf)),
            "tags": [],
            "textAlignment": "justify",
            "textScale": 1,
            "zoomMode": "bestFit",
        }))
        z.writestr(f"{doc}.pagedata", "\n".join([""] * pages))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("markdown", type=Path)
    p.add_argument("-o", "--output", type=Path, help="output .rmdoc (default: alongside input)")
    p.add_argument("-n", "--name", help="document name on the tablet (default: filename)")
    p.add_argument("--paper", nargs=2, default=PAPER, metavar=("W", "H"), help=f"page size (default: {PAPER[0]} {PAPER[1]})")
    p.add_argument("--margin", default=MARGIN, help=f"geometry spec (default: {MARGIN})")
    p.add_argument("--font-size", default="12pt")
    p.add_argument("--pdf-engine", default="xelatex")
    p.add_argument("pandoc_args", nargs="*", help="extra args passed to pandoc (after --)")
    a = p.parse_args()

    out = a.output or a.markdown.with_suffix(".rmdoc")
    pdf = md_to_pdf(a.markdown, a.paper, a.margin, a.font_size, a.pdf_engine, a.pandoc_args)
    write_rmdoc(pdf, a.name or a.markdown.stem, out)
    print(f"{out} ({page_count(pdf)} pages)")


if __name__ == "__main__":
    sys.exit(main())
