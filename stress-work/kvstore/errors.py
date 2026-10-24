"""Exceptions used across the kvstore package."""


class KVError(Exception):
    """Base class for every kvstore error."""


class ProtocolError(KVError):
    """A request line could not be parsed into a known command."""


class CommandError(KVError):
    """A syntactically valid command could not be executed."""
