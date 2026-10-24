"""Poll a source directory and rebuild the site whenever it changes.

This is intentionally simple: no filesystem notification APIs, just a poll
every couple of seconds that compares ``(mtime, size)`` for every Markdown
file. Because :func:`sitegen.site.build_site` is incremental, a poll that finds
a change only re-renders the pages that actually changed.
"""

from __future__ import annotations

import time

from .site import build_site, discover_state

DEFAULT_INTERVAL = 2.0


def watch(
    source_dir,
    output_dir,
    interval=DEFAULT_INTERVAL,
    max_polls=None,
    sleep=time.sleep,
    poll_hook=None,
    on_build=None,
    **build_kwargs
):
    """Build once, then rebuild whenever a source file changes.

    Stops when *max_polls* polls have run, when *poll_hook* returns ``False``,
    or when the caller interrupts it. ``sleep`` is injectable so tests do not
    have to wait in real time. Returns the list of :class:`BuildResult` objects,
    one per build, starting with the initial build.
    """
    build_kwargs.setdefault("incremental", True)
    results = []

    def run():
        result = build_site(source_dir, output_dir, **build_kwargs)
        results.append(result)
        if on_build is not None:
            on_build(result)
        return result

    run()
    state = discover_state(source_dir)

    polls = 0
    while max_polls is None or polls < max_polls:
        if poll_hook is not None and poll_hook(polls) is False:
            break
        sleep(interval)
        polls += 1
        new_state = discover_state(source_dir)
        if new_state != state:
            state = new_state
            run()

    return results
