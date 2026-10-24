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

# generate a 300-page synthetic site, then build it
python3 -m sitegen sample /tmp/sample-site
python3 -m sitegen build /tmp/sample-site /tmp/sample-public --base-url https://example.com

# rebuild on every change, polling every 2 seconds
python3 -m sitegen build sitegen/example/content sitegen/example/public --watch
```

Options:

- `--template PATH` — custom HTML template (defaults to a built-in one)
- `--title NAME` — site title used in `<title>` and the header
- `--drafts` — also build pages whose front matter sets `draft: true`
- `--base-url URL` — absolute site URL used for links in the RSS feed
- `--no-feed` — do not write `feed.xml`
- `--no-incremental` — rebuild every page instead of only the changed ones
- `--watch` — keep running and rebuild when source files change
- `--interval SECONDS` — poll interval for `--watch` (default `2.0`)

The builder writes one `.html` file per `.md` file, generates an `index.html`
unless the content folder already contains an `index.md`, and writes an RSS 2.0
`feed.xml`.

### Incremental builds

Builds are incremental by default. A manifest, `.sitegen-manifest.json`, is
written into the output directory and records:

- a content hash for every source file
- the template hash, site title and draft setting
- a *navigation key* covering page titles and URLs
- a key for the generated index and RSS feed

On the next build only pages whose source hash changed are re-rendered; unchanged
pages are restored from the manifest without being read again. A changed
template, title, draft setting or navigation forces a full rebuild, removed
sources have their stale output deleted, and a missing or corrupt manifest
simply triggers a full rebuild. `--no-incremental` bypasses the manifest.

### Watch mode

`--watch` builds once, then polls every `--interval` seconds (2 by default),
comparing each source file's `(mtime, size)`. When something changes it runs an
incremental build, so only the affected pages are rewritten.

### Synthetic sample site

`python3 -m sitegen sample DIR` writes a deterministic tree of Markdown files
(`--pages`, default 300; `--seed`, default 1234) grouped into `section-NN/`
folders. The content exercises front matter, headings, lists, links, code blocks
and blockquotes, and each page carries an increasing `date` so the RSS feed has
real publication dates.

### RSS feed

Every build writes `feed.xml` (RSS 2.0) listing all published pages except the
index. Item links use `--base-url` when set, and dates come from each page's
front-matter `date`. A page can opt out with `feed: false`.

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
- `sitegen/site.py` — page loading, navigation, index, manifest and `build_site`
- `sitegen/feed.py` — RSS 2.0 feed generation
- `sitegen/sample.py` — synthetic site generator
- `sitegen/watch.py` — polling watch mode
- `sitegen/cli.py` — the `python3 -m sitegen` command line interface
- `sitegen/htmlutil.py` — escaping, slugify and relative-URL helpers
- `sitegen/example/` — demo content, template and stylesheet

### Tests

The suite uses the standard-library `unittest` framework only:

```bash
cd stress-work && python3 -m unittest discover -s sitegen -t .
```

Each module has a matching `test_*.py` covering parsing, rendering, templating,
the builder, incremental builds, the RSS feed, the synthetic sampler, watch mode
and the CLI.
