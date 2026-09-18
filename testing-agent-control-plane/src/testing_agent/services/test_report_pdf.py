from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Flowable,
    LongTable,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

PDF_FONT_NAME = "STSong-Light"


def ensure_pdf_font() -> None:
    if PDF_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(PDF_FONT_NAME))


def test_report_pdf_styles() -> dict[str, ParagraphStyle]:
    ensure_pdf_font()
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TestReportTitle",
            parent=sample["Title"],
            fontName=PDF_FONT_NAME,
            fontSize=20,
            leading=26,
            alignment=TA_CENTER,
            spaceAfter=14,
        ),
        "heading1": ParagraphStyle(
            "TestReportHeading1",
            parent=sample["Heading1"],
            fontName=PDF_FONT_NAME,
            fontSize=16,
            leading=22,
            spaceBefore=12,
            spaceAfter=8,
        ),
        "heading2": ParagraphStyle(
            "TestReportHeading2",
            parent=sample["Heading2"],
            fontName=PDF_FONT_NAME,
            fontSize=13,
            leading=18,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "TestReportBody",
            parent=sample["BodyText"],
            fontName=PDF_FONT_NAME,
            fontSize=10.5,
            leading=16,
            spaceAfter=6,
        ),
        "code": ParagraphStyle(
            "TestReportCode",
            parent=sample["Code"],
            fontName=PDF_FONT_NAME,
            fontSize=9,
            leading=12,
            leftIndent=4,
            rightIndent=4,
            backColor=colors.HexColor("#F5F5F5"),
        ),
        "table": ParagraphStyle(
            "TestReportTable",
            parent=sample["BodyText"],
            fontName=PDF_FONT_NAME,
            fontSize=9,
            leading=12,
        ),
    }


def markdown_inline_to_paragraph_text(text: str) -> str:
    value = escape(text.strip())
    while "**" in value:
        value = value.replace("**", "<b>", 1)
        if "**" not in value:
            value = value.replace("<b>", "**", 1)
            break
        value = value.replace("**", "</b>", 1)
    return value


def table_cells(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def is_table_separator(cells: list[str]) -> bool:
    return bool(cells) and all(set(cell.replace(":", "").strip()) <= {"-"} for cell in cells)


def consume_table(
    lines: list[str],
    start_index: int,
    styles: dict[str, ParagraphStyle],
) -> tuple[LongTable, int]:
    rows: list[list[str]] = []
    index = start_index
    while index < len(lines) and lines[index].strip().startswith("|"):
        rows.append(table_cells(lines[index]))
        index += 1

    if len(rows) > 1 and is_table_separator(rows[1]):
        rows.pop(1)

    max_columns = max(len(row) for row in rows)
    normalized = [
        row + [""] * (max_columns - len(row)) for row in rows if any(cell.strip() for cell in row)
    ]
    data = [
        [Paragraph(markdown_inline_to_paragraph_text(cell), styles["table"]) for cell in row]
        for row in normalized
    ]
    table = LongTable(data, repeatRows=1 if len(data) > 1 else 0, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), PDF_FONT_NAME),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F2F5")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9D9D9")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table, index


def markdown_to_pdf_bytes(markdown: str, title: str = "测试报告") -> bytes:
    styles = test_report_pdf_styles()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=title,
    )
    story: list[Flowable] = [Paragraph(escape(title), styles["title"])]
    lines = markdown.splitlines()
    index = 0
    in_code = False
    code_lines: list[str] = []

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                story.append(Preformatted("\n".join(code_lines), styles["code"]))
                story.append(Spacer(1, 6))
                code_lines = []
                in_code = False
            else:
                in_code = True
            index += 1
            continue

        if in_code:
            code_lines.append(line)
            index += 1
            continue

        if not stripped:
            story.append(Spacer(1, 4))
            index += 1
            continue

        if stripped.startswith("|") and "|" in stripped[1:]:
            table, index = consume_table(lines, index, styles)
            story.append(table)
            story.append(Spacer(1, 8))
            continue

        if stripped.startswith("# "):
            story.append(
                Paragraph(markdown_inline_to_paragraph_text(stripped[2:]), styles["heading1"])
            )
        elif stripped.startswith("## "):
            story.append(
                Paragraph(markdown_inline_to_paragraph_text(stripped[3:]), styles["heading2"])
            )
        elif stripped.startswith("- ") or stripped.startswith("* "):
            story.append(
                Paragraph("- " + markdown_inline_to_paragraph_text(stripped[2:]), styles["body"])
            )
        elif stripped[:3].replace(".", "").isdigit() and ". " in stripped[:5]:
            story.append(Paragraph(markdown_inline_to_paragraph_text(stripped), styles["body"]))
        else:
            story.append(Paragraph(markdown_inline_to_paragraph_text(stripped), styles["body"]))
        index += 1

    if code_lines:
        story.append(Preformatted("\n".join(code_lines), styles["code"]))

    document.build(story)
    return buffer.getvalue()
