"""Secure text extraction for supported RAG document formats.

Why it exists: the RAG contracts define parsing but no implementation can
validate and extract PDF, DOCX, or UTF-8 text content. This module performs
CPU/blocking parser work only and is called through ``asyncio.to_thread`` by
the document service.
"""

from pathlib import Path
from zipfile import BadZipFile, ZipFile

import pymupdf
from docx import Document as load_docx
from docx.document import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph

from src.search_engine.rag.contracts import ParsedDocument, ParsedPage

PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
TXT_CONTENT_TYPE = "text/plain"


class DocumentParseError(ValueError):
    """Base class for safe client-facing parsing failures."""


class CorruptDocumentError(DocumentParseError):
    """Raised when bytes do not form the declared document type."""


class EmptyDocumentError(DocumentParseError):
    """Raised when a document contains no extractable text."""


class ScannedPdfError(DocumentParseError):
    """Raised when a PDF needs OCR, which is intentionally out of scope."""


class UnsupportedContentTypeError(DocumentParseError):
    """Raised when no Phase 2 parser supports the declared MIME type."""


class RagDocumentParser:
    """Validate and extract supported documents without performing OCR."""

    def __init__(self, *, max_docx_uncompressed_bytes: int) -> None:
        self._max_docx_uncompressed_bytes = max_docx_uncompressed_bytes

    def parse(self, path: Path, content_type: str) -> ParsedDocument:
        if content_type == PDF_CONTENT_TYPE:
            return self._parse_pdf(path)
        if content_type == DOCX_CONTENT_TYPE:
            return self._parse_docx(path)
        if content_type == TXT_CONTENT_TYPE:
            return self._parse_txt(path)
        raise UnsupportedContentTypeError("Unsupported document content type.")

    def _parse_pdf(self, path: Path) -> ParsedDocument:
        data = path.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise CorruptDocumentError("File content is not a valid PDF.")

        try:
            with pymupdf.open(stream=data, filetype="pdf") as document:
                if document.needs_pass:
                    raise CorruptDocumentError("Password-protected PDFs are unsupported.")

                pages = tuple(
                    ParsedPage(
                        text=page.get_text("text", sort=True),
                        page_number=index + 1,
                    )
                    for index, page in enumerate(document)
                )
                metadata = _clean_metadata(document.metadata)
                metadata["page_count"] = document.page_count
        except DocumentParseError:
            raise
        except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
            raise CorruptDocumentError("PDF is corrupted or unreadable.") from exc

        text = "\n\n".join(page.text for page in pages)
        if not text.strip():
            raise ScannedPdfError(
                "PDF contains no extractable text; scanned or image-only PDFs require OCR."
            )
        return ParsedDocument(text=text, pages=pages, metadata=metadata)

    def _parse_docx(self, path: Path) -> ParsedDocument:
        _validate_docx_container(path, self._max_docx_uncompressed_bytes)
        try:
            document = load_docx(path)
            blocks: list[str] = []
            for item in document.iter_inner_content():
                if isinstance(item, Paragraph):
                    blocks.append(item.text)
                elif isinstance(item, Table):
                    blocks.extend(
                        "\t".join(cell.text for cell in row.cells)
                        for row in item.rows
                    )
            text = "\n".join(blocks)
            metadata = _docx_metadata(document)
        except (BadZipFile, KeyError, PackageNotFoundError, ValueError) as exc:
            raise CorruptDocumentError("DOCX is corrupted or unreadable.") from exc

        if not text.strip():
            raise EmptyDocumentError("Document contains no extractable text.")
        return ParsedDocument(
            text=text,
            pages=(ParsedPage(text=text),),
            metadata=metadata,
        )

    def _parse_txt(self, path: Path) -> ParsedDocument:
        data = path.read_bytes()
        if b"\x00" in data:
            raise CorruptDocumentError("TXT file contains binary data.")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CorruptDocumentError("TXT files must use UTF-8 encoding.") from exc

        if any(ord(character) < 32 and character not in "\t\n\r" for character in text):
            raise CorruptDocumentError("TXT file contains unsupported control bytes.")
        if not text.strip():
            raise EmptyDocumentError("Document contains no extractable text.")
        return ParsedDocument(
            text=text,
            pages=(ParsedPage(text=text),),
            metadata={"encoding": "utf-8"},
        )
def _validate_docx_container(path: Path, max_uncompressed_bytes: int) -> None:
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            if sum(member.file_size for member in members) > max_uncompressed_bytes:
                raise CorruptDocumentError("DOCX expands beyond the safe size limit.")
            if any(member.flag_bits & 0x1 for member in members):
                raise CorruptDocumentError("Encrypted DOCX files are unsupported.")
            names = {member.filename for member in members}
            required = {"[Content_Types].xml", "word/document.xml"}
            if not required.issubset(names):
                raise CorruptDocumentError("File content is not a valid DOCX.")
            bad_member = archive.testzip()
            if bad_member is not None:
                raise CorruptDocumentError("DOCX is corrupted or unreadable.")
    except BadZipFile as exc:
        raise CorruptDocumentError("File content is not a valid DOCX.") from exc


def _clean_metadata(raw: dict[str, object] | None) -> dict[str, str | int]:
    if not raw:
        return {}
    return {
        key: str(value)
        for key, value in raw.items()
        if value not in (None, "")
    }


def _docx_metadata(document: DocxDocument) -> dict[str, str]:
    properties = document.core_properties
    values = {
        "title": properties.title,
        "author": properties.author,
        "subject": properties.subject,
        "language": properties.language,
    }
    return {key: value for key, value in values.items() if value}
