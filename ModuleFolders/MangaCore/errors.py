"""MangaCore exceptions."""


class MangaCoreError(Exception):
    """Base exception for MangaCore."""


class ProjectFormatError(MangaCoreError):
    """Raised when a manga project on disk is malformed."""


class UnsupportedInputError(MangaCoreError):
    """Raised when a manga input source is unsupported."""


class OperationError(MangaCoreError):
    """Raised when an editor operation cannot be applied."""
