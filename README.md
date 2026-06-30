<pre>
                __  _                         ____
   ____  ____  / /_(_)___  ____  ____  __  __/ / /
  / __ \/ __ \/ __/ / __ \/ __ \/ __ \/ / / / / /
 / / / / /_/ / /_/ / /_/ / / / / /_/ / /_/ / / /
/_/ /_/\____/\__/_/\____/_/ /_/ .___/\__,_/_/_/
                             /_/
</pre>

Scrapes any public Notion page into a fully offline, self-contained static HTML
snapshot — images, stylesheets, PDFs, and all.

Maintained by [ruskicoder](https://github.com/ruskicoder).

---

## Quick Start

### CLI (Docker — recommended)

```bash
pip install -r requirements.txt    # only needed for rich output
python pull.py -i              # interactive
python pull.py <url> <dest>    # one-shot
```

Auto-builds the Docker image, runs the scraper, copies the output to your
destination, and cleans up.

### Direct (no Docker)

```bash
pip install -r requirements.txt
python notionpull https://user.notion.site/MyPage-abc123
```

Output lands in `./snapshots/<page-id>/`.

---

## CLI Tool (`pull.py`)

A zero-fuss wrapper that manages the entire Docker lifecycle:

| Step | What happens |
|---|---|
| 1. Check | Verifies Docker is running |
| 2. Build | Builds the image (cached after first run) |
| 3. Run | Launches the scraper in a disposable container |
| 4. Extract | Copies output to your destination folder |
| 5. Cleanup | Removes container + temp files |

### Terminal mode

```bash
# minimal
python pull.py https://user.notion.site/MyPage-abc123 ./backups/my-page

# dark mode, 30s timeout
python pull.py -d -t 30 https://user.notion.site/MyPage-abc123 .

# show browser, disable cache
python pull.py -b -c https://user.notion.site/MyPage-abc123 ./output
```

### Interactive mode

```bash
python pull.py -i
```

Prompts for URL, destination, dark mode, timeout, and caching — with clickable
links and styled output when `rich` is installed.

### All flags

```
positional arguments:
  url                   Notion page URL
  dest                  Destination folder

scraping options:
  -d, --dark-mode       Scrape in dark mode
  -t, --timeout SEC     Page load timeout (default: 60)
  -b, --show-browser    Show browser window (not headless)
  -c, --disable-caching Disable asset caching

docker options:
  --rebuild             Force rebuild the Docker image
  --no-cleanup          Keep container + temp files for inspection
  --remove-image        Also remove the Docker image on cleanup

mode:
  -i, --interactive     Interactive mode with prompts
```

### Cleanup behavior

| Flag | Container | `snapshots/` dir | Docker image |
|---|---|---|---|
| *(default)* | Removed | Removed | Preserved |
| `--no-cleanup` | Preserved | Preserved | Preserved |
| `--remove-image` | Removed | Removed | Removed |

---

## Direct Usage (no Docker)

```bash
# basic
python notionpull https://user.notion.site/MyPage-abc123

# dark mode
python notionpull --dark-mode https://user.notion.site/MyPage-abc123

# with options
python notionpull -b -t 30 -c https://user.notion.site/MyPage-abc123

# help
python notionpull --help
```

### Direct flags

| Flag | Description |
|---|---|
| `-b, --show-browser` | Show browser window (default: headless) |
| `-d, --dark-mode` | Scrape in dark mode |
| `-t, --timeout TIMEOUT` | Page load timeout in seconds (default: 10) |
| `-c, --disable-caching` | Disable asset caching between runs |

---

## Docker

### Manual (docker compose)

```bash
# build + start
docker compose build
docker compose run --rm main python notionpull <url>

# or use the CLI wrapper instead (auto-manages this)
python pull.py <url> <dest>
```

The image bundles Chrome + Python 3.11 + all dependencies. The project source is
bind-mounted at `/workspace` so code changes take effect immediately — no
rebuild needed between runs.

### Dockerfile

The image is based on `python:3.11-slim-bookworm` with Chrome installed
from the official `.deb`. Dependencies are installed via `pip` (Python 3.11's
native pip) with `--no-cache-dir`.

---

## How It Works

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐
│  Notion  │◄───│  Chrome via  │◄───                │  __main__.py │◄───│  CLI/wrapper │
│   page   │    │  Selenium    │    │  (BS4+reqs)  │    └───────────┘
└──────────┘    └──────────────┘    └──────────────┘
                        │                   │
                        ▼                   ▼
                 ┌──────────────┐    ┌──────────────┐
                 │  injection   │    │   assets/    │
                 │  .js / .css  │    │  (local)     │
                 └──────────────┘    └──────────────┘
```

1. **Selenium** loads the page in headless Chrome and waits for all content
2. **Toggle blocks** are expanded recursively so hidden content is captured
3. **BeautifulSoup** parses the DOM, strips javascript/overlays
4. **Assets** (images, CSS, PDFs, fonts) are downloaded and linked locally
5. **Injections** — custom CSS (mobile layout, fixes) + JS (toggle interactivity,
   anchor links) — are embedded
6. **Subpages** are discovered via internal links and scraped recursively (BFS)
7. **Output** is a fully offline `index.html` + `assets/` directory

---

## Output

```
snapshots/<page-name>/
├── index.html              # main page
├── assets/
│   ├── <hash>.png          # downloaded images
│   ├── <hash>.css          # notion stylesheets
│   ├── <name>.pdf          # file attachments
│   ├── injection.js        # toggle/anchor interactivity
│   └── injection.css       # mobile + layout fixes
└── <subpage-name>.html     # linked subpages
```

Each page is self-contained — open `index.html` in any browser. No server
required.

---

## Supported Blocks

| Category | Status |
|---|---|
| Text / headings / lists | ✓ |
| Toggle blocks (nested) | ✓ |
| Inline page links | ✓ |
| Images | ✓ |
| Stylesheets / fonts | ✓ |
| PDF file attachments | ✓ |
| Code blocks | ✓ |
| Bookmark blocks | ✓ |
| Databases (table, board, gallery, list, calendar) | Partial |
| Embedded video / audio | ✗ |
| Table view subpage links | Glitchy |

See `docs/progress.md` for the full audit.

---

## Limitations

- **Public pages only** — Notion's client-side auth means private pages can't be
  scraped
- **Embedded media** — mp4/mp3 embeds call Notion's internal API and aren't
  captured
- **Database views** — table view has horizontal glitches; subpage links in
  databases may not render correctly
- **No JavaScript** — all `<script>` tags are stripped (except the injected
  toggle/anchor JS)
- **Chrome version** — the `webdriver_manager` auto-detects the matching
  ChromeDriver, so Chrome must stay reasonably up-to-date in the image

---

## License

MIT
