"""File-watching with a simple polling loop (2 seconds by default).

No third-party watchdog library is used: the watcher hashes the contents of
every Markdown source file and rebuilds when the snapshot changes. Polling is
deliberately simple and portable.
"""

import hashlib
import os
import time

from .builder import MARKDOWN_EXTENSIONS, SiteBuilder

__all__ = ["Watcher", "DEFAULT_INTERVAL"]

DEFAULT_INTERVAL = 2.0


class Watcher:
    """Poll a source directory and rebuild the site when it changes."""

    def __init__(self, source_dir, output_dir, interval=DEFAULT_INTERVAL, builder=None, **builder_kwargs):
        self.source_dir = os.path.abspath(source_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.interval = interval
        self.builder = builder if builder is not None else SiteBuilder(
            self.source_dir, self.output_dir, **builder_kwargs
        )

    # -- snapshotting -----------------------------------------------------
    def snapshot(self):
        """Return ``{relative_path: content_hash}`` for all markdown sources."""
        state = {}
        for root, dirs, files in os.walk(self.source_dir):
            dirs[:] = sorted(
                d
                for d in dirs
                if not d.startswith(".")
                and os.path.abspath(os.path.join(root, d)) != self.output_dir
            )
            for name in files:
                if name.startswith(".") or not name.lower().endswith(MARKDOWN_EXTENSIONS):
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, self.source_dir).replace(os.sep, "/")
                try:
                    with open(full, "rb") as handle:
                        digest = hashlib.sha1(handle.read()).hexdigest()
                except OSError:
                    digest = ""
                state[rel] = digest
        return state

    @staticmethod
    def changes(previous, current):
        """Return ``(added, modified, removed)`` sorted lists of paths."""
        added = sorted(set(current) - set(previous))
        removed = sorted(set(previous) - set(current))
        modified = sorted(
            name for name in set(previous) & set(current) if previous[name] != current[name]
        )
        return added, modified, removed

    # -- loop -------------------------------------------------------------
    def build(self):
        return self.builder.build()

    def run(self, max_polls=None, sleep=time.sleep, stop_event=None, on_build=None):
        """Build once, then poll every ``interval`` seconds until stopped.

        ``max_polls`` bounds the number of polls (useful for tests), ``sleep``
        is injectable and ``stop_event`` may be any object with ``is_set()``.
        Returns the number of polls performed.
        """
        previous = self.snapshot()
        first = self.build()
        if on_build is not None:
            on_build(first)

        polls = 0
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            if max_polls is not None and polls >= max_polls:
                break
            sleep(self.interval)
            polls += 1
            current = self.snapshot()
            if current != previous:
                previous = current
                result = self.build()
                if on_build is not None:
                    on_build(result)
        return polls
