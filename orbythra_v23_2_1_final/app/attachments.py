"""Workspace-scoped file attachments for the Unified Answer Console.

Users can upload txt / md / csv / json / code / pdf / docx files. The text is
extracted server-side and kept in an in-memory, workspace-isolated store with a
TTL. The unified answer pipeline treats an attachment as a *direct* evidence
source (``source_type="attachment"``) so the agent can answer questions about
the file and the V1/V5.1 evidence gates can bind claims to its text.

Nothing is written to disk and binary content is discarded after extraction.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from xml.etree import ElementTree

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import SETTINGS
from app.security import Principal, require_minimum_role

router = APIRouter(prefix="/v11/answer/files", tags=["v11-unified-answer"])
_REQUIRE_OPERATOR = require_minimum_role("operator")

# Uploads are also bounded by the global request-body limit (ORBYTHRA_MAX_BODY_BYTES).
MAX_FILE_BYTES = min(int(os.getenv("ORBYTHRA_ATTACHMENT_MAX_BYTES", str(8 * 1024 * 1024))), SETTINGS.max_body_bytes)
MAX_TEXT_CHARS = int(os.getenv("ORBYTHRA_ATTACHMENT_MAX_CHARS", "200000"))
MAX_FILES_PER_WORKSPACE = int(os.getenv("ORBYTHRA_ATTACHMENT_MAX_FILES", "20"))
TTL_SECONDS = int(os.getenv("ORBYTHRA_ATTACHMENT_TTL_SECONDS", str(6 * 3600)))

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".log", ".xml", ".html", ".htm", ".sql", ".sh", ".bat", ".ps1",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cs",
    ".rb", ".php", ".swift", ".scala", ".r", ".m", ".lua", ".dart", ".env", ".dockerfile",
}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}
_WS = re.compile(r"[ \t\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")


@dataclass
class Attachment:
    attachment_id: str
    workspace_id: str
    filename: str
    media_type: str
    size_bytes: int
    text: str
    sha256: str
    uploaded_at: int
    kind: str
    warnings: list[str] = field(default_factory=list)


class AttachmentSummary(BaseModel):
    attachment_id: str
    filename: str
    kind: str
    size_bytes: int
    text_chars: int
    sha256: str
    uploaded_at: int
    preview: str
    warnings: list[str]


class _AttachmentStore:
    def __init__(self) -> None:
        self._items: dict[str, Attachment] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        deadline = int(time.time()) - TTL_SECONDS
        for key in [k for k, v in self._items.items() if v.uploaded_at < deadline]:
            self._items.pop(key, None)

    def put(self, item: Attachment) -> None:
        with self._lock:
            self._purge()
            owned = [v for v in self._items.values() if v.workspace_id == item.workspace_id]
            if len(owned) >= MAX_FILES_PER_WORKSPACE:
                oldest = min(owned, key=lambda v: v.uploaded_at)
                self._items.pop(oldest.attachment_id, None)
            self._items[item.attachment_id] = item

    def get(self, workspace_id: str, attachment_id: str) -> Attachment | None:
        with self._lock:
            self._purge()
            item = self._items.get(attachment_id)
            return item if item is not None and item.workspace_id == workspace_id else None

    def list(self, workspace_id: str) -> list[Attachment]:
        with self._lock:
            self._purge()
            return sorted(
                (v for v in self._items.values() if v.workspace_id == workspace_id),
                key=lambda v: v.uploaded_at,
            )

    def delete(self, workspace_id: str, attachment_id: str) -> bool:
        with self._lock:
            item = self._items.get(attachment_id)
            if item is None or item.workspace_id != workspace_id:
                return False
            del self._items[attachment_id]
            return True

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


ATTACHMENTS = _AttachmentStore()


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANK_LINES.sub("\n\n", text).strip()


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1254", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_pdf(data: bytes, warnings: list[str]) -> str:
    try:
        from pypdf import PdfReader  # optional dependency
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise HTTPException(415, "pdf_support_requires_pypdf") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(415, "pdf_is_encrypted") from exc
        pages: list[str] = []
        for index, page in enumerate(reader.pages):
            pages.append(page.extract_text() or "")
            if sum(len(p) for p in pages) > MAX_TEXT_CHARS:
                warnings.append(f"pdf_truncated_after_page:{index + 1}")
                break
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(415, "pdf_parse_failed") from exc
    text = "\n\n".join(f"[page {i + 1}]\n{p.strip()}" for i, p in enumerate(pages) if p.strip())
    if not text:
        warnings.append("pdf_has_no_extractable_text:scanned_or_image_only")
    return text


def _extract_docx(data: bytes, warnings: list[str]) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise HTTPException(415, "docx_parse_failed") from exc
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise HTTPException(415, "docx_parse_failed") from exc
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{{{ns['w']}}}p"):
        parts = [node.text or "" for node in paragraph.iter() if node.tag in (f"{{{ns['w']}}}t", f"{{{ns['w']}}}tab")]
        line = "".join("\t" if not p else p for p in parts).strip()
        if line:
            paragraphs.append(line)
    if not paragraphs:
        warnings.append("docx_has_no_text")
    return "\n".join(paragraphs)


def extract_text(filename: str, data: bytes) -> tuple[str, str, list[str]]:
    """Return (kind, text, warnings) for a supported file."""
    warnings: list[str] = []
    suffix = PurePosixPath(filename.lower()).suffix
    if not suffix and filename.lower() in {"dockerfile", "makefile", "readme", "license"}:
        suffix = ".txt"
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, f"unsupported_attachment_type:{suffix or 'none'}")
    if suffix == ".pdf":
        kind, text = "pdf", _extract_pdf(data, warnings)
    elif suffix == ".docx":
        kind, text = "docx", _extract_docx(data, warnings)
    else:
        if b"\x00" in data[:4096]:
            raise HTTPException(415, "binary_content_not_supported")
        kind, text = "text", _decode_text(data)
    text = _clean(text)
    if len(text) > MAX_TEXT_CHARS:
        warnings.append(f"text_truncated_to:{MAX_TEXT_CHARS}")
        text = text[:MAX_TEXT_CHARS]
    return kind, text, warnings


def _summary(item: Attachment) -> AttachmentSummary:
    return AttachmentSummary(
        attachment_id=item.attachment_id,
        filename=item.filename,
        kind=item.kind,
        size_bytes=item.size_bytes,
        text_chars=len(item.text),
        sha256=item.sha256,
        uploaded_at=item.uploaded_at,
        preview=item.text[:280],
        warnings=item.warnings,
    )


def store_attachment(workspace_id: str, filename: str, data: bytes, media_type: str = "") -> Attachment:
    if not data:
        raise HTTPException(400, "empty_attachment")
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "attachment_too_large")
    safe_name = PurePosixPath(filename.replace("\\", "/")).name[:200] or "attachment"
    kind, text, warnings = extract_text(safe_name, data)
    if not text:
        warnings.append("attachment_has_no_text")
    item = Attachment(
        attachment_id="file-" + uuid.uuid4().hex,
        workspace_id=workspace_id,
        filename=safe_name,
        media_type=media_type[:120],
        size_bytes=len(data),
        text=text,
        sha256=hashlib.sha256(data).hexdigest(),
        uploaded_at=int(time.time()),
        kind=kind,
        warnings=warnings,
    )
    ATTACHMENTS.put(item)
    return item


def resolve_attachments(workspace_id: str, attachment_ids: list[str]) -> tuple[list[Attachment], list[str]]:
    found: list[Attachment] = []
    missing: list[str] = []
    for attachment_id in dict.fromkeys(attachment_ids):
        item = ATTACHMENTS.get(workspace_id, attachment_id)
        if item is None:
            missing.append(attachment_id)
        else:
            found.append(item)
    return found, missing


@router.post("", response_model=AttachmentSummary, status_code=201)
async def upload(file: UploadFile = File(...), principal: Principal = Depends(_REQUIRE_OPERATOR)) -> AttachmentSummary:
    data = await file.read(MAX_FILE_BYTES + 1)
    item = store_attachment(principal.workspace_id, file.filename or "attachment", data, file.content_type or "")
    return _summary(item)


@router.get("", response_model=list[AttachmentSummary])
def list_files(principal: Principal = Depends(_REQUIRE_OPERATOR)) -> list[AttachmentSummary]:
    return [_summary(item) for item in ATTACHMENTS.list(principal.workspace_id)]


@router.delete("/{attachment_id}", status_code=204)
def delete_file(attachment_id: str, principal: Principal = Depends(_REQUIRE_OPERATOR)) -> None:
    if not ATTACHMENTS.delete(principal.workspace_id, attachment_id):
        raise HTTPException(404, "attachment_not_found")
