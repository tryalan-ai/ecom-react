---
title: About
weight: 90
---

# About sitegen

sitegen is a deliberately small static site generator used to exercise
end-to-end coding workflows. It parses Markdown by hand and renders pages
through a minimal template engine.

## Design notes

- The Markdown parser is split into an inline layer and a block layer
- Templates escape values by default; `{{{ triple braces }}}` inject raw HTML
- The site builder is pure Python and writes files deterministically

---

Questions? Open an issue in the repository.
