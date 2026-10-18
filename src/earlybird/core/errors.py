"""Exceptions shared across the public plane."""


class EarlybirdError(Exception):
    """Base class for expected, handled failures."""


class AdapterError(EarlybirdError):
    """A source could not be fetched or parsed. Recorded in health; never fails a whole run."""


class NotFoundError(AdapterError):
    """The source says this company/slug does not exist (HTTP 404). Flags a dead registry entry."""
