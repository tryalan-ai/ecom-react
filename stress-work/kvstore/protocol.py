"""A tiny line oriented text protocol.

Requests are single lines terminated by ``\\n``.  The first token is the
command (case-insensitive); keys are single tokens that must not contain
whitespace; for ``SET`` the value is the remainder of the line and may contain
spaces.  Responses are single lines: they begin with ``+`` on success and ``-``
on error.

Commands::

    PING                    -> +PONG
    SET <key> <value...>    -> +OK
    GET <key>               -> +VALUE <value...> | +NIL
    DEL <key>               -> +OK 1 | +OK 0
    EXISTS <key>            -> +OK 1 | +OK 0
    KEYS                    -> +KEYS [<key> ...]
    LEN                     -> +LEN <n>
    SNAPSHOT                -> +OK
    QUIT                    -> +BYE   (connection closed)
"""

from .errors import CommandError, ProtocolError

#: Longest request line accepted, in bytes.
MAX_LINE = 65536

#: Response prefixes.
OK_PREFIX = "+"
ERR_PREFIX = "-"


def parse_request(line):
    """Split a raw request line into ``(command, args)``.

    ``args`` is the raw remainder of the line after the first space; callers
    decide how to interpret it.  Raises :class:`ProtocolError` for a blank
    line.
    """
    if not isinstance(line, str):
        raise ProtocolError("request must be text")
    line = line.rstrip("\r\n")
    if not line.strip():
        raise ProtocolError("empty command")
    command, _, args = line.partition(" ")
    return command.upper(), args


def format_line(text):
    """Encode a response line (adding the trailing newline)."""
    return (text + "\n").encode("utf-8")


def _err(message):
    return format_line("%sERR %s" % (ERR_PREFIX, message))


def _require_key(args):
    token = args.strip()
    if not token:
        raise CommandError("missing key")
    if any(ch.isspace() for ch in token):
        raise CommandError("invalid key")
    return token


def execute(store, line):
    """Execute one request against ``store``.

    Returns ``(response_bytes, should_close)``.
    """
    try:
        command, args = parse_request(line)
    except ProtocolError as exc:
        return _err(str(exc)), False

    try:
        return _dispatch(store, command, args)
    except CommandError as exc:
        return _err(str(exc)), False
    except (TypeError, ValueError) as exc:
        return _err(str(exc)), False


def _dispatch(store, command, args):
    if command == "PING":
        return format_line("+PONG"), False

    if command == "SET":
        key, sep, value = args.partition(" ")
        if not key or any(ch.isspace() for ch in key):
            raise CommandError("missing key")
        store.set(key, value if sep else "")
        return format_line("+OK"), False

    if command == "GET":
        key = _require_key(args)
        value = store.get(key)
        if value is None:
            return format_line("+NIL"), False
        return format_line("+VALUE %s" % value), False

    if command == "DEL":
        key = _require_key(args)
        removed = store.delete(key)
        return format_line("+OK %d" % (1 if removed else 0)), False

    if command == "EXISTS":
        key = _require_key(args)
        present = key in store
        return format_line("+OK %d" % (1 if present else 0)), False

    if command == "KEYS":
        keys = store.keys()
        if keys:
            return format_line("+KEYS %s" % " ".join(keys)), False
        return format_line("+KEYS"), False

    if command == "LEN":
        return format_line("+LEN %d" % len(store)), False

    if command == "SNAPSHOT":
        store.snapshot()
        return format_line("+OK"), False

    if command == "QUIT":
        return format_line("+BYE"), True

    raise CommandError("unknown command %r" % (command,))
