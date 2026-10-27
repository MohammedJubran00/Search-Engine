"""Private filesystem storage for uploaded RAG source documents.

Why it exists: client filenames must never determine filesystem paths. This
module generates opaque references, enforces the byte limit while copying, and
keeps every resolved path beneath the configured private storage root.
"""

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


class FileTooLargeError(ValueError):
    """Raised when streamed upload bytes exceed the configured limit."""


class EmptyUploadError(ValueError):
    """Raised when an uploaded file has zero bytes."""


class StorageOperationError(OSError):
    """Raised when private storage cannot safely complete an operation."""


@dataclass(frozen=True, slots=True)
class StorageTarget:
    """Opaque database reference plus private temporary/final paths."""

    reference: str
    temporary_path: Path
    final_path: Path


class DocumentStorage:
    """Store generated filenames beneath one resolved private root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def new_target(self, extension: str) -> StorageTarget:
        token = uuid.uuid4().hex
        reference = f"{token}{extension}"
        final_path = self._resolve(reference)
        temporary_path = self._resolve(f".{token}.uploading")
        return StorageTarget(reference, temporary_path, final_path)

    def write_limited(
        self,
        source: BinaryIO,
        target: StorageTarget,
        max_bytes: int,
    ) -> int:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            source.seek(0)
            total = 0
            with target.temporary_path.open("xb") as destination:
                while chunk := source.read(64 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise FileTooLargeError(
                            f"Document exceeds the {max_bytes}-byte upload limit."
                        )
                    destination.write(chunk)
            if total == 0:
                raise EmptyUploadError("Uploaded document is empty.")
            return total
        except (FileTooLargeError, EmptyUploadError):
            self.remove_path(target.temporary_path)
            raise
        except OSError as exc:
            self.remove_path(target.temporary_path)
            raise StorageOperationError("Unable to store the uploaded document.") from exc

    def promote(self, target: StorageTarget) -> None:
        try:
            os.replace(target.temporary_path, target.final_path)
        except OSError as exc:
            raise StorageOperationError("Unable to finalize document storage.") from exc

    def path_for(self, reference: str) -> Path:
        return self._resolve(reference)

    def quarantine(self, reference: str) -> tuple[Path, Path] | None:
        original = self._resolve(reference)
        if not original.exists():
            return None
        quarantined = self._resolve(f".{uuid.uuid4().hex}.deleting")
        try:
            os.replace(original, quarantined)
        except OSError as exc:
            raise StorageOperationError("Unable to remove document storage.") from exc
        return original, quarantined

    def restore(self, quarantined: tuple[Path, Path] | None) -> None:
        if quarantined is None:
            return
        original, temporary = quarantined
        if temporary.exists():
            os.replace(temporary, original)

    def remove_reference(self, reference: str) -> None:
        self.remove_path(self._resolve(reference))

    @staticmethod
    def remove_path(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def _resolve(self, reference: str) -> Path:
        if not reference or Path(reference).name != reference:
            raise StorageOperationError("Invalid private storage reference.")
        candidate = (self.root / reference).resolve()
        if candidate.parent != self.root:
            raise StorageOperationError("Invalid private storage reference.")
        return candidate
