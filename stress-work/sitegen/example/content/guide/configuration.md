---
title: Configuration
weight: 11
tags: [guide, reference]
---

# Configuration

The generator is driven by command-line flags and per-page front matter.

## Command line

The recognised flags are:

- `--template PATH` — use a custom HTML template
- `--title NAME` — set the site title used in `<title>` and the header
- `--drafts` — include pages marked `draft: true`

## Front matter keys

```yaml
title: Display title
weight: 10
tags: [a, b]
draft: false
```

Pages are ordered in the navigation by `weight`, then by filename.
