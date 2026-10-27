from io import BytesIO
import textwrap
import zipfile
from xml.etree import ElementTree as ET


def _pdf_escape(text):
    return text.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(text, title="Smart Study Companion Export"):
    lines = []
    for source_line in text.splitlines() or [""]:
        source_line = source_line.expandtabs(4)
        if not source_line:
            lines.append("")
            continue
        indent = len(source_line) - len(source_line.lstrip(" "))
        wrapped = textwrap.wrap(
            source_line,
            width=92,
            initial_indent="" if indent else "",
            subsequent_indent=" " * min(indent, 12),
            replace_whitespace=False,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        )
        lines.extend(wrapped or [""])

    lines.insert(0, title)
    lines.insert(1, "")
    page_lines = [lines[index:index + 50] for index in range(0, len(lines), 50)] or [[title]]
    objects = [None, b"<< /Type /Catalog /Pages 2 0 R >>", None, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    page_ids = []

    for page in page_lines:
        page_id = len(objects)
        content_id = page_id + 1
        page_ids.append(page_id)
        commands = ["BT", "/F1 10 Tf", "50 755 Td", "14 TL"]
        for line in page:
            commands.append(f"({_pdf_escape(line)}) Tj")
            commands.append("T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", "replace")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
    output = BytesIO()
    output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects[1:], start=1):
        offsets.append(output.tell())
        output.write(f"{object_id} 0 obj\n".encode())
        output.write(body)
        output.write(b"\nendobj\n")
    xref_offset = output.tell()
    output.write(f"xref\n0 {len(objects)}\n".encode())
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(
        f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    )
    return output.getvalue()


def make_docx(text, title="Smart Study Companion Export"):
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ET.register_namespace("w", ns)
    q = lambda name: f"{{{ns}}}{name}"
    document = ET.Element(q("document"))
    body = ET.SubElement(document, q("body"))

    for index, line in enumerate([title, "", *text.splitlines()]):
        paragraph = ET.SubElement(body, q("p"))
        if index == 0:
            properties = ET.SubElement(paragraph, q("pPr"))
            style = ET.SubElement(properties, q("pStyle"))
            style.set(q("val"), "Title")
        run = ET.SubElement(paragraph, q("r"))
        if line.startswith("    "):
            run_props = ET.SubElement(run, q("rPr"))
            fonts = ET.SubElement(run_props, q("rFonts"))
            fonts.set(q("ascii"), "Consolas")
            fonts.set(q("hAnsi"), "Consolas")
        node = ET.SubElement(run, q("t"))
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        node.text = line

    section = ET.SubElement(body, q("sectPr"))
    ET.SubElement(section, q("pgSz"), {q("w"): "12240", q("h"): "15840"})
    xml_document = ET.tostring(document, encoding="utf-8", xml_declaration=True)
    content_types = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''
    relationships = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", xml_document)
    return output.getvalue()
