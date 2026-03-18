"""Custom exception types for the application domain."""


class UserNotFoundError(Exception):
    """Raised when a user with the requested ID does not exist."""


class DuplicateEmailError(Exception):
    """Raised when a user with the given email already exists."""


class DatabaseError(Exception):
    """Raised when an unexpected database-level error occurs."""


class CacheError(Exception):
    """Raised when a non-critical cache operation fails."""
