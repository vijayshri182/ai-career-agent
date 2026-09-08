"""File storage abstraction."""

from abc import ABC, abstractmethod
from pathlib import Path
from uuid import UUID

from backend.core.config import Settings
from backend.core.security_service import get_security_service


class FileStorage(ABC):
    """Abstract file storage backend."""

    @abstractmethod
    async def write(
        self, file_id: UUID, content: bytes, content_type: str, original_filename: str
    ) -> str:
        """Store content and return storage path/identifier."""

    @abstractmethod
    async def read(self, path: str) -> bytes:
        """Read content by storage path/identifier."""

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete stored content."""


class LocalFileStorage(FileStorage):
    """Local filesystem storage for development."""

    def __init__(self, settings: Settings) -> None:
        self.base_path = settings.storage_local_path
        self.encrypt = settings.storage_encrypt_files
        self.security = get_security_service()

    def _path_for(self, file_id: UUID) -> Path:
        return self.base_path / str(file_id)[0:2] / str(file_id)

    async def write(
        self, file_id: UUID, content: bytes, content_type: str, original_filename: str
    ) -> str:
        target = self._path_for(file_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = content
        if self.encrypt:
            encrypted = self.security.encrypt(data.decode("latin-1"))
            if encrypted is None:
                raise ValueError("Failed to encrypt file content")
            data = encrypted.encode("utf-8")
        target.write_bytes(data)
        return str(target.relative_to(self.base_path))

    async def read(self, path: str) -> bytes:
        target = self.base_path / path
        data = target.read_bytes()
        if self.encrypt:
            decrypted = self.security.decrypt(data.decode("utf-8"))
            if decrypted is None:
                return b""
            return decrypted.encode("latin-1")
        return data

    async def delete(self, path: str) -> None:
        target = self.base_path / path
        if target.exists():
            target.unlink()


def make_storage(settings: Settings) -> FileStorage:
    if settings.storage_provider == "local":
        return LocalFileStorage(settings)
    if settings.storage_provider in {"s3", "minio"}:
        raise NotImplementedError("S3/MinIO storage adapter not implemented in Phase 1")
    raise ValueError(f"Unknown storage provider: {settings.storage_provider}")
