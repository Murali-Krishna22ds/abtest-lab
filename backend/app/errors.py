"""Application errors that map to clean HTTP responses."""
from __future__ import annotations


class AppError(Exception):
    """A request the server understood but cannot satisfy (bad data, bad parameters, missing dataset)."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
