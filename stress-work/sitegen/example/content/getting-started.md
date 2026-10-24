---
title: Getting started
weight: 1
tags: [guide]
---

# Getting started

Point sitegen at a folder of Markdown files and an output folder:

```bash
python3 -m sitegen build content public --title "My Docs"
```

That writes one HTML file per Markdown file, plus an `index.html`.

## Writing pages

Each page may begin with front matter:

```markdown
---
title: My page
weight: 2
tags: [a, b]
---
```

The rest of the file is ordinary Markdown. Headings get stable anchors, so you
can link to a section with `#writing-pages`.

## Lists

1. Write some Markdown
2. Run the generator
3. Open `public/index.html`
