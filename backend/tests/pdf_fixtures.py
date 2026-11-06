"""PDF helpers that only tests need."""

from io import BytesIO

from pypdf import PdfReader, PdfWriter


def encrypt_pdf(data: bytes, password: str) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(BytesIO(data)))
    writer.encrypt(password)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
