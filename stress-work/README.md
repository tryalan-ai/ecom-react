# stress-work

A sandbox for long-running, realistic coding tasks. The first project living
here is **sitegen**, a static site generator written from scratch.

## sitegen

`sitegen` turns a folder of Markdown files into a static HTML site. It uses
only the Python standard library — no Markdown library, no template library, no
pip installs. Markdown parsing, the template engine and the site builder are all
implemented in this repository.

### Usage

```bash
cd stress-work

# build a site from content/ into public/
python3 -m sitegen build sitegen/example/content sitegen/example/public \
    --template sitegen/example/template.html \
    --title "sitegen docs"
```

Options:

- `--template PATH` — custom HTML template (defaults to a built-in one)
- `--title NAME` — site title used in `<title>` and the header
- `--drafts` — also build pages whose front matter sets `draft: true`

The builder writes one `.html` file per `.md` file and generates an
`index.html` unless the content folder already contains an `index.md`.

### Markdown features

- Front matter delimited by `---` (`title`, `weight`, `tags`, `draft`, ...)
- ATX headings `#`–`######` with stable anchor ids
- Paragraphs, unordered and ordered (including nested) lists
- Fenced (```` ``` ````, `~~~`) and indented code blocks with language classes
- Blockquotes and thematic breaks
- Inline emphasis, strong, code spans, links, images and autolinks

### Package layout

- `sitegen/frontmatter.py` — front matter parsing
- `sitegen/inline.py` — inline Markdown parser and renderer
- `sitegen/blocks.py` — block-level parser, AST and HTML renderer
- `sitegen/template.py` — `{{ }}`, `{{{ }}}`, `{% if %}`, `{% for %}` engine
- `sitegen/site.py` — page loading, navigation, index page and `build_site`
- `sitegen/cli.py` — the `python3 -m sitegen` command line interface
- `sitegen/htmlutil.py` — escaping, slugify and relative-URL helpers
- `sitegen/example/` — demo content, template and stylesheet

### Tests

The suite uses the standard-library `unittest` framework only:

```bash
cd stress-work && python3 -m unittest discover -s sitegen -t .
```

Each module has a matching `test_*.py` covering parsing, rendering, templating,
the builder and the CLI.
