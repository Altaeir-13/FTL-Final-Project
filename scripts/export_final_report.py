"""Export the complete FTL Markdown report to selectable, illustrated A4 PDF.

Requires Pandoc (GFM reader), ReportLab, Pillow and pypdf. Uses only local,
versioned figures and system fonts; it never downloads or recomputes science.
The build directory receives the Pandoc AST and a machine-readable fidelity
audit. Render the resulting PDF with Poppler and inspect every page before
delivery; text checks are not a substitute for layout review.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

from PIL import Image as PILImage
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image, KeepTogether, Paragraph, Preformatted, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)


REPOSITORY = "https://github.com/Altaeir-13/FTL-Final-Project"
PUBLIC_COMMIT = "ad107d0c29c63ad9eb9f91a5970d96906676e3df"
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN
INK = colors.HexColor("#173d34")
RULE = colors.HexColor("#b8c8bb")
NORMAL = colors.HexColor("#243a2f")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def typography(text: str) -> str:
    """Use printable ASCII hyphens, retaining all numerical values and units."""
    return text.translate(str.maketrans({"–": "-", "—": "-", "‑": "-", "−": "-"}))


def esc(text: str) -> str:
    return html.escape(typography(text), quote=True)


def canonical(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", typography(text)))


def plain(inlines: list[dict]) -> str:
    chunks = []
    for node in inlines:
        kind, value = node["t"], node.get("c")
        if kind == "Str":
            chunks.append(value)
        elif kind in {"Space", "SoftBreak", "LineBreak"}:
            chunks.append(" ")
        elif kind == "Code":
            chunks.append(value[1])
        elif kind in {"Strong", "Emph", "Strikeout", "Superscript", "Subscript"}:
            chunks.append(plain(value))
        elif kind in {"Link", "Image"}:
            if kind == "Link":
                chunks.append(plain(value[1]))
        elif kind == "Quoted":
            chunks.append('"' + plain(value[1]) + '"')
        else:
            raise ValueError(f"Unsupported inline text: {kind}")
    return "".join(chunks)


def register_fonts(directory: str | None) -> tuple[str, str]:
    if directory:
        font_dir = Path(directory)
    elif Path("C:/Windows/Fonts/arial.ttf").exists():
        font_dir = Path("C:/Windows/Fonts")
    else:
        font_dir = Path("/usr/share/fonts/truetype/dejavu")
    if (font_dir / "arial.ttf").exists():
        files = {"Aqua": "arial.ttf", "Aqua-Bold": "arialbd.ttf", "Aqua-Italic": "ariali.ttf", "Aqua-BoldItalic": "arialbi.ttf", "Aqua-Code": "consola.ttf"}
    else:
        files = {"Aqua": "DejaVuSans.ttf", "Aqua-Bold": "DejaVuSans-Bold.ttf", "Aqua-Italic": "DejaVuSans-Oblique.ttf", "Aqua-BoldItalic": "DejaVuSans-BoldOblique.ttf", "Aqua-Code": "DejaVuSansMono.ttf"}
    for name, filename in files.items():
        path = font_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing system font {path}; use --font-dir.")
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily("Aqua", normal="Aqua", bold="Aqua-Bold", italic="Aqua-Italic", boldItalic="Aqua-BoldItalic")
    return str(font_dir), "Arial" if "arial.ttf" in files.values() else "DejaVu Sans"


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["BodyText"]
    common = dict(fontName="Aqua", textColor=NORMAL, alignment=TA_LEFT, splitLongWords=1, allowWidows=0, allowOrphans=0)
    result = {
        "body": ParagraphStyle("ReportBody", parent=base, fontSize=10.2, leading=14.2, spaceAfter=7, **common),
        "title": ParagraphStyle("ReportTitle", fontName="Aqua-Bold", textColor=INK, fontSize=23, leading=28, spaceBefore=10, spaceAfter=17, keepWithNext=True),
        "heading": ParagraphStyle("ReportHeading", fontName="Aqua-Bold", textColor=INK, fontSize=14.2, leading=18.5, spaceBefore=14, spaceAfter=8, keepWithNext=True),
        "caption": ParagraphStyle("ReportCaption", fontName="Aqua-Italic", textColor=colors.HexColor("#415348"), fontSize=8.8, leading=12, spaceBefore=4, spaceAfter=10, allowWidows=0, allowOrphans=0),
        "cell": ParagraphStyle("ReportCell", fontName="Aqua", textColor=NORMAL, fontSize=8.4, leading=11.4, spaceAfter=0, splitLongWords=1),
        "tablehead": ParagraphStyle("ReportTableHead", fontName="Aqua-Bold", textColor=INK, fontSize=8.5, leading=11.6, spaceAfter=0, splitLongWords=1),
        "reference": ParagraphStyle("ReportReference", fontName="Aqua", textColor=NORMAL, fontSize=9.3, leading=13, spaceAfter=7, leftIndent=13, firstLineIndent=-13, allowWidows=0, allowOrphans=0, splitLongWords=1),
        "code": ParagraphStyle("ReportCode", fontName="Aqua-Code", fontSize=8.3, leading=11.5, textColor=NORMAL, backColor=colors.HexColor("#f2f5f0"), borderColor=RULE, borderWidth=.4, borderPadding=9, spaceBefore=4, spaceAfter=12),
    }
    return result


class Report(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable, "bookmark", None):
            self.canv.bookmarkPage(flowable.bookmark)
            self.canv.addOutlineEntry(flowable.getPlainText(), flowable.bookmark, level=0)


class Exporter:
    def __init__(self, source: Path, ast: dict):
        self.source, self.ast = source, ast
        self.s = styles()
        self.figures: list[dict] = []
        self.expected: list[dict] = []
        self.tables: list[dict] = []
        self.links: set[str] = set()

    def target(self, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme:
            if parsed.scheme not in {"http", "https", "mailto"}:
                raise ValueError(f"Unsupported link scheme: {value}")
            target = value
        elif value.startswith("#"):
            target = f"{REPOSITORY}/blob/{PUBLIC_COMMIT}/docs/{self.source.name}{value}"
        else:
            target = urljoin(f"{REPOSITORY}/blob/{PUBLIC_COMMIT}/docs/", quote(value, safe="/#?=&%"))
        self.links.add(target)
        return target

    def inline(self, nodes: list[dict], *, in_table: bool = False) -> str:
        parts = []
        for node in nodes:
            kind, value = node["t"], node.get("c")
            if kind == "Str":
                parts.append(esc(value))
            elif kind in {"Space", "SoftBreak"}:
                parts.append(" ")
            elif kind == "LineBreak":
                parts.append("<br/>")
            elif kind in {"Strong", "Emph", "Superscript", "Subscript"}:
                tag = {"Strong": "b", "Emph": "i", "Superscript": "super", "Subscript": "sub"}[kind]
                parts.append(f"<{tag}>{self.inline(value, in_table=in_table)}</{tag}>")
            elif kind == "Code":
                size = 7.8 if in_table else 9.0
                parts.append(f'<font name="Aqua-Code" size="{size}">{esc(value[1])}</font>')
            elif kind == "Link":
                parts.append(f'<a href="{html.escape(self.target(value[2][0]), quote=True)}" color="#235d49"><u>{self.inline(value[1], in_table=in_table)}</u></a>')
            elif kind == "Quoted":
                parts.append('"' + self.inline(value[1], in_table=in_table) + '"')
            elif kind == "Image":
                raise ValueError("Images must be rendered as flowables, not inline text.")
            else:
                raise ValueError(f"Unsupported inline formatting: {kind}")
        return "".join(parts)

    def image(self, node: dict, width: float) -> Image:
        relative = node["c"][2][0]
        if urlparse(relative).scheme:
            raise ValueError("Remote images are forbidden; use the versioned local figure.")
        path = (self.source.parent / relative).resolve()
        if not path.is_relative_to(self.source.parent.resolve()) or not path.is_file():
            raise ValueError(f"Image outside report sources or missing: {relative}")
        with PILImage.open(path) as raster:
            original_width, original_height = raster.size
        scale = min(width / original_width, 150 * mm / original_height)
        item = Image(str(path), width=original_width * scale, height=original_height * scale)
        item.hAlign = "CENTER"
        self.figures.append({"path": relative, "sha256": digest(path), "pixels": [original_width, original_height], "display_points": [item.drawWidth, item.drawHeight]})
        return item

    def record(self, kind: str, text: str):
        if text.strip():
            self.expected.append({"kind": kind, "text": typography(text)})

    def cell(self, blocks: list[dict], width: float, header: bool):
        items = []
        for block in blocks:
            if block["t"] not in {"Para", "Plain"}:
                raise ValueError(f"Unsupported table block: {block['t']}")
            nodes = block["c"]
            if len(nodes) == 1 and nodes[0]["t"] == "Image":
                items.append(self.image(nodes[0], width - 12))
            else:
                items.append(Paragraph(self.inline(nodes, in_table=True), self.s["tablehead" if header else "cell"]))
        return items

    def table(self, block: dict) -> Table:
        value = block["c"]
        head_rows = value[3][1]
        body_rows = [row for body in value[4] for row in body[2] + body[3]]
        foot_rows = value[5][1]
        rows = head_rows + body_rows + foot_rows
        column_count = len(value[2])
        # Widths are layout only; no cell value or precision is changed.
        title = plain(head_rows[0][1][0][4][0]["c"])
        weights = {
            "Fonte": [19, 31, 50], "Método": [23, 38, 39],
            "Evidência congelada": [65, 35], "Pivô": [12, 12, 34, 21, 21],
            "Data": [17, 52, 15, 16], "18/07/2023": [50, 50],
        }.get(title, [100 / column_count] * column_count)
        widths = [CONTENT_WIDTH * weight / sum(weights) for weight in weights]
        contents = []
        for row_number, row in enumerate(rows):
            cells = row[1]
            if len(cells) != column_count or any(cell[2:4] != [1, 1] for cell in cells):
                raise ValueError("Merged table cells need explicit support.")
            contents.append([self.cell(cell[4], widths[i], row_number < len(head_rows)) for i, cell in enumerate(cells)])
            texts = [" ".join(plain(part["c"]) for part in cell[4]) for cell in cells]
            for text in texts:
                self.record("table-cell", text)
        self.tables.append({"header": title, "columns": column_count, "rows": len(rows), "body_rows": len(body_rows)})
        result = Table(contents, colWidths=widths, repeatRows=len(head_rows), hAlign="LEFT", splitByRow=1, splitInRow=0, spaceBefore=5, spaceAfter=10)
        result.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, len(head_rows) - 1), colors.HexColor("#e8f0e7")),
            ("LINEBELOW", (0, 0), (-1, len(head_rows) - 1), .8, INK),
            ("LINEBELOW", (0, len(head_rows)), (-1, -1), .35, RULE),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("ROWBACKGROUNDS", (0, len(head_rows)), (-1, -1), [colors.white, colors.HexColor("#f7f9f5")]),
        ]))
        return result

    def blocks(self, blocks: list[dict]) -> list:
        result = []
        index = 0
        while index < len(blocks):
            block = blocks[index]
            kind, value = block["t"], block.get("c")
            if kind == "Header":
                text = plain(value[2]); self.record("heading", text)
                paragraph = Paragraph(self.inline(value[2]), self.s["title" if value[0] == 1 else "heading"])
                if value[0] > 1:
                    paragraph.bookmark = value[1][0]
                result.append(paragraph)
            elif kind in {"Para", "Plain"}:
                if len(value) == 1 and value[0]["t"] == "Image":
                    figure = [Spacer(1, 5), self.image(value[0], CONTENT_WIDTH)]
                    if index + 1 < len(blocks) and blocks[index + 1]["t"] == "Para" and plain(blocks[index + 1]["c"]).startswith("Figura "):
                        index += 1; caption = blocks[index]["c"]
                        self.record("caption", plain(caption))
                        figure.append(Paragraph(self.inline(caption), self.s["caption"]))
                    result.append(KeepTogether(figure))
                else:
                    text = plain(value); self.record("paragraph", text)
                    style = "caption" if text.startswith(("Figura ", "Tabela ")) else "body"
                    result.append(Paragraph(self.inline(value), self.s[style]))
            elif kind == "Table":
                table = self.table(block)
                if index + 1 < len(blocks) and blocks[index + 1]["t"] == "Para" and plain(blocks[index + 1]["c"]).startswith("Figura "):
                    index += 1; caption = blocks[index]["c"]
                    self.record("caption", plain(caption))
                    result.append(KeepTogether([table, Paragraph(self.inline(caption), self.s["caption"])]))
                else:
                    result.append(table)
            elif kind == "CodeBlock":
                text = typography(value[1]); self.record("code", text)
                result.append(Preformatted(text, self.s["code"]))
            elif kind == "OrderedList":
                start = value[0][0]
                for offset, item in enumerate(value[1]):
                    for entry in item:
                        if entry["t"] not in {"Para", "Plain"}:
                            raise ValueError("Unsupported reference-list block.")
                        text = f"{start + offset}. {plain(entry['c'])}"; self.record("reference", text)
                        result.append(Paragraph(f"{start + offset}. {self.inline(entry['c'])}", self.s["reference"]))
            else:
                raise ValueError(f"Unsupported Markdown block: {kind}")
            index += 1
        return result


def page_chrome(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(RULE); canvas.setLineWidth(.5)
    canvas.line(MARGIN, PAGE_HEIGHT - 14 * mm, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 14 * mm)
    canvas.setFillColor(INK); canvas.setFont("Aqua-Bold", 8)
    canvas.drawString(MARGIN, PAGE_HEIGHT - 11 * mm, "AQUACLIMA | RELATÓRIO FINAL FTL")
    canvas.setFont("Aqua", 7.5); canvas.setFillColor(colors.HexColor("#435a4a"))
    canvas.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 11 * mm, "Ciência aberta - versão pública 17/11/2026")
    canvas.line(MARGIN, 14 * mm, PAGE_WIDTH - MARGIN, 14 * mm)
    canvas.drawString(MARGIN, 10 * mm, "Paracatu: estudo concluído | Guadalupe: prova exploratória")
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 10 * mm, f"Página {document.page}")
    canvas.restoreState()


def audit_pdf(output: Path, exporter: Exporter, font_name: str, build_dir: Path) -> dict:
    reader = PdfReader(output)
    page_texts = [page.extract_text(extraction_mode="plain") or "" for page in reader.pages]
    cleaned = []
    for text in page_texts:
        for label in ["AQUACLIMA | RELATÓRIO FINAL FTL", "Ciência aberta - versão pública 17/11/2026", "Paracatu: estudo concluído | Guadalupe: prova exploratória"]:
            text = text.replace(label, "")
        text = re.sub(r"Página \d+", "", text)
        cleaned.append(text)
    extracted = canonical("\n".join(cleaned))
    missing = [entry for entry in exporter.expected if canonical(entry["text"]) not in extracted]
    # Text fidelity checks every authored paragraph, caption, reference and cell.
    # The raster review remains mandatory to verify positions and page breaks.
    if missing:
        (build_dir / "fidelity-missing.json").write_text(json.dumps(missing, ensure_ascii=False, indent=2), encoding="utf-8")
        raise AssertionError(f"{len(missing)} source text blocks absent from PDF; see fidelity-missing.json")
    for page in reader.pages:
        assert abs(float(page.mediabox.width) - PAGE_WIDTH) < 1 and abs(float(page.mediabox.height) - PAGE_HEIGHT) < 1
    assert len(exporter.figures) == 6, "Expected four scientific plots and the two real Guadalupe scenes."
    assert len(exporter.tables) == 6, "Expected every Markdown table, including the real-image comparison."
    assert len(reader.outline) == 22, "Every numbered report section must be bookmarked."
    image_objects = {name for page in reader.pages for name in page.images.keys()}
    annotations = sum(len(page.get("/Annots", [])) for page in reader.pages)
    assert len(image_objects) == 6 and annotations >= len(exporter.links), "Expected all six embedded figures and clickable references."
    report = {
        "source": exporter.source.as_posix(), "source_sha256": digest(exporter.source),
        "output": output.as_posix(), "pdf_sha256": digest(output), "pages": len(reader.pages),
        "page_format": "A4 portrait", "font": font_name, "selectable_text": True,
        "text_blocks_checked": len(exporter.expected), "missing_text_blocks": 0,
        "tables": exporter.tables, "figures": exporter.figures,
        "links": sorted(exporter.links), "link_annotations": annotations,
        "public_commit": PUBLIC_COMMIT,
        "visual_review": "Required separately: render and inspect every page after final generation.",
    }
    (build_dir / "fidelity.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (build_dir / "report-text.txt").write_text("\n\f\n".join(page_texts), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("docs/relatorio-final-ftl.md"))
    parser.add_argument("--output", type=Path, default=Path("docs/relatorio-final-ftl.pdf"))
    parser.add_argument("--build-dir", type=Path, default=Path("build/release-report"))
    parser.add_argument("--pandoc", default=os.environ.get("AQUACLIMA_PANDOC") or shutil.which("pandoc") or "pandoc")
    parser.add_argument("--font-dir", default=None)
    args = parser.parse_args()
    args.source = args.source.resolve(); args.output = args.output.resolve(); args.build_dir = args.build_dir.resolve()
    args.build_dir.mkdir(parents=True, exist_ok=True); args.output.parent.mkdir(parents=True, exist_ok=True)
    font_dir, font_name = register_fonts(args.font_dir)
    process = subprocess.run([args.pandoc, "--from=gfm", "--to=json", str(args.source)], check=True, capture_output=True, text=True, encoding="utf-8")
    ast = json.loads(process.stdout)
    (args.build_dir / "report-ast.json").write_text(json.dumps(ast, ensure_ascii=False, indent=2), encoding="utf-8")
    exporter = Exporter(args.source, ast)
    document = Report(str(args.output), pagesize=A4, rightMargin=MARGIN, leftMargin=MARGIN, topMargin=21 * mm, bottomMargin=21 * mm,
                      title="AquaClima: monitoramento espectral reproduzível de áreas agrícolas irrigadas", author="Randerson Sousa de Sá Nunes", subject=f"Relatório final FTL - main {PUBLIC_COMMIT}")
    document.build(exporter.blocks(ast["blocks"]), onFirstPage=page_chrome, onLaterPages=page_chrome)
    report = audit_pdf(args.output, exporter, font_name, args.build_dir)
    print(json.dumps({"pages": report["pages"], "text_blocks": report["text_blocks_checked"], "tables": len(report["tables"]), "figures": len(report["figures"]), "pdf_sha256": report["pdf_sha256"], "source_sha256": report["source_sha256"], "font_directory": font_dir}, ensure_ascii=False))


if __name__ == "__main__":
    main()
