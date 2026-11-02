#!/usr/bin/env python3
"""Build the submission package from docs/REPORT.md.

    python tools/build_submission.py diagrams   render every ```mermaid block to docs/diagrams/*.png
    python tools/build_submission.py export     build/REPORT.export.md (mermaid blocks -> images)
    python tools/build_submission.py pdf        submission/DevOps_MiniProject_Report.pdf
    python tools/build_submission.py docx       submission/DevOps_MiniProject_Report.docx
    python tools/build_submission.py all        everything above, in order

Needs node/npx (mermaid-cli), pandoc and Chrome. docs/REPORT.md itself is never modified:
GitHub renders its Mermaid block, only the exported copy uses images.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DIAGRAMS = ROOT / "docs" / "diagrams"
SUBMISSION = ROOT / "submission"
REPORT = ROOT / "docs" / "REPORT.md"
EXPORT_MD = BUILD / "REPORT.export.md"
CSS = ROOT / "docs" / "report-print.css"
STEM = "DevOps_MiniProject_Report"
MERMAID_SOURCES = [ROOT / "README.md", REPORT, ROOT / "docs" / "architecture.md"]
MERMAID_BLOCK = re.compile(r"```mermaid\r?\n(.*?)\r?\n```", re.DOTALL)
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "google-chrome",
    "chromium",
]


def find_chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        found = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if found:
            return found
    sys.exit("error: Chrome or Edge not found")


def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        sys.exit(f"error: '{tool}' not found on PATH")
    return path


def diagram_name(source: Path, index: int) -> str:
    return f"{source.stem}-{index}"


def render_diagrams() -> list[str]:
    """Render every mermaid block in the source files. Returns the list of PNG names."""
    npx = need("npx")
    (BUILD / "mermaid").mkdir(parents=True, exist_ok=True)
    DIAGRAMS.mkdir(parents=True, exist_ok=True)
    config = BUILD / "puppeteer.json"
    config.write_text(json.dumps({"executablePath": find_chrome(), "args": ["--no-sandbox"]}))
    env = {**os.environ, "PUPPETEER_SKIP_DOWNLOAD": "1"}
    names = []
    for source in MERMAID_SOURCES:
        blocks = MERMAID_BLOCK.findall(source.read_text(encoding="utf-8"))
        for number, code in enumerate(blocks, start=1):
            name = diagram_name(source, number)
            src, out = BUILD / "mermaid" / f"{name}.mmd", DIAGRAMS / f"{name}.png"
            if source == REPORT:
                # A4 portrait is narrow: draw left-to-right diagrams top-to-bottom in the export.
                code = code.replace("flowchart LR", "flowchart TB")
                code = code.replace("direction LR", "direction TB")
            src.write_text(code + "\n", encoding="utf-8")
            cmd = [npx, "-y", "@mermaid-js/mermaid-cli@12", "-i", str(src), "-o", str(out)]
            cmd += ["-t", "default", "-b", "white", "-s", "2", "-p", str(config), "-q"]
            print(f"rendering {name} ...", flush=True)
            subprocess.run(cmd, check=True, env=env)
            names.append(name)
    return names


def build_export_markdown() -> Path:
    """REPORT.md copy for export: mermaid blocks become images, paths relative to build/."""
    text = REPORT.read_text(encoding="utf-8")
    counter = iter(range(1, 1000))

    def to_image(_match: re.Match) -> str:
        name = diagram_name(REPORT, next(counter))
        return f"![Figure: {name}](../docs/diagrams/{name}.png)"

    text = MERMAID_BLOCK.sub(to_image, text)
    text = text.replace("](screenshots/", "](../docs/screenshots/")
    BUILD.mkdir(exist_ok=True)
    EXPORT_MD.write_text(text, encoding="utf-8")
    print(f"wrote {EXPORT_MD.relative_to(ROOT)}")
    return EXPORT_MD


def build_html() -> Path:
    pandoc = need("pandoc")
    html = BUILD / f"{STEM}.html"
    cmd = [pandoc, str(EXPORT_MD), "-f", "gfm", "-t", "html5", "--standalone", "--embed-resources"]
    cmd += ["--css", str(CSS), "--metadata", "pagetitle=DevOps Mini Project Report"]
    cmd += ["--resource-path", str(BUILD), "-o", str(html)]
    subprocess.run(cmd, check=True)
    return html


def build_pdf() -> Path:
    html = build_html()
    SUBMISSION.mkdir(exist_ok=True)
    pdf = SUBMISSION / f"{STEM}.pdf"
    cmd = [find_chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer"]
    cmd += [f"--user-data-dir={BUILD / 'chrome-profile'}", f"--print-to-pdf={pdf}"]
    cmd += ["--virtual-time-budget=20000", html.as_uri()]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"wrote {pdf.relative_to(ROOT)}")
    return pdf


def build_docx() -> Path:
    SUBMISSION.mkdir(exist_ok=True)
    docx = SUBMISSION / f"{STEM}.docx"
    cmd = [need("pandoc"), str(EXPORT_MD), "-f", "gfm", "--resource-path", str(BUILD)]
    cmd += ["-o", str(docx)]
    subprocess.run(cmd, check=True)
    print(f"wrote {docx.relative_to(ROOT)}")
    return docx


def main(argv: list[str]) -> int:
    step = argv[0] if argv else "all"
    if step in ("diagrams", "all"):
        render_diagrams()
    if step in ("export", "pdf", "docx", "all"):
        build_export_markdown()
    if step in ("pdf", "all"):
        build_pdf()
    if step in ("docx", "all"):
        build_docx()
    if step not in ("diagrams", "export", "pdf", "docx", "all"):
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
