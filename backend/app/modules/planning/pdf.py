from __future__ import annotations

import textwrap
import unicodedata


def build_simple_pdf(*, title: str, sections: list[tuple[str, list[str]]]) -> bytes:
    """Gera PDF textual, autocontido e sem dependência externa.

    O formato usa Helvetica padrão. Conteúdo é normalizado para ASCII para
    manter compatibilidade com o conjunto de caracteres básico do PDF.
    """

    lines = [title, ""]
    for heading, items in sections:
        lines.extend([heading, *items, ""])

    pages: list[list[str]] = []
    page: list[str] = []
    for line in lines:
        wrapped = textwrap.wrap(_pdf_text(line), width=92) or [""]
        for item in wrapped:
            if len(page) >= 48:
                pages.append(page)
                page = []
            page.append(item)
    pages.append(page or [""])

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [" + b" ".join(f"{4 + index * 2} 0 R".encode() for index in range(len(pages))) + b"] /Count " + str(len(pages)).encode() + b" >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, page_lines in enumerate(pages):
        content = _page_content(page_lines)
        page_id = 4 + index * 2
        content_id = page_id + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        objects.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")

    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, content in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{object_id} 0 obj\n".encode())
        result.extend(content)
        result.extend(b"\nendobj\n")

    xref_at = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF".encode())
    return bytes(result)


def _page_content(lines: list[str]) -> bytes:
    content = ["BT", "/F1 10 Tf", "48 800 Td", "14 TL"]
    for index, line in enumerate(lines):
        if index:
            content.append("T*")
        content.append(f"({_escape(line)}) Tj")
    content.append("ET")
    return "\n".join(content).encode("latin-1", errors="replace")


def _pdf_text(value: str) -> str:
    return unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
