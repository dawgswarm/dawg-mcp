# dawg-mcp

An [MCP](https://modelcontextprotocol.io) server that gives AI agents (Claude Code, Codex, …)
direct access to the **DAWG** platform.

> **🇷🇺 Built for Runet.** DAWG is purpose-built for the Russian segment of the web: Russian
> residential proxies and geolocation (city slugs like `moskva`, `spb`, …) and stealth
> fingerprints tuned for RU sites. If your agent needs to browse or scrape Russian sites
> (Yandex, Ozon, Wildberries, Avito, gosuslugi, banks, …), this is the tool it was made for.

- 🌐 **Remote stealth browser** — provision an on-demand Chromium (RU proxy, geo, stealth baked in)
  and drive it with snapshot/click/type/screenshot tools.
- 🔎 **Web scraping** — single-page scrape plus crawl/batch jobs returning clean markdown/text/html.
- 📊 **Account usage** — read the current plan, limits and consumption for your API key.

The browser tools mirror the interaction model of the official
[`@playwright/mcp`](https://github.com/microsoft/playwright-mcp): the agent takes an **accessibility
snapshot** of the page (an ARIA tree with `[ref=eN]` markers), then targets elements by `ref`. This
is far more reliable and token-efficient than screenshot-and-guess.

Browsers run on DAWG infrastructure — **no local browser is launched or downloaded**; the server
only attaches to the remote Chromium over CDP.

## Requirements

- Python ≥ 3.10
- A DAWG API key (`X-API-Key`) from https://dawgswarm.ru
- [`uv`](https://docs.astral.sh/uv/) (recommended) for `uvx`/`uv run`

## Install / run

```bash
# Recommended — straight from PyPI (fast: downloads a prebuilt wheel)
uvx dawg-mcp

# Or with pip
pip install dawg-mcp && dawg-mcp

# From GitHub (no PyPI), pinned to a tag:
uvx --from git+https://github.com/dawgswarm/dawg-mcp@v0.1.0 dawg-mcp

# Local checkout (development) — run from the repo root
uv run dawg-mcp

# As a module
python -m dawg_mcp
```

`DAWG_API_KEY` must be set in the environment. **No `playwright install` is needed** — the server
connects to a remote browser and never launches Chromium locally.

## Register with an agent

### Claude Code

Project scope — commit `.mcp.json` (it reads `${DAWG_API_KEY}` from your shell):

```json
{
  "mcpServers": {
    "dawg": {
      "type": "stdio",
      "command": "uvx",
      "args": ["dawg-mcp"],
      "env": {
        "DAWG_API_KEY": "${DAWG_API_KEY}",
        "DAWG_BASE_URL": "${DAWG_BASE_URL:-https://dawgswarm.ru}"
      }
    }
  }
}
```

Or via the CLI:

```bash
claude mcp add dawg --scope user --env DAWG_API_KEY=your_key -- uvx dawg-mcp

# local working tree:
claude mcp add dawg --scope user --env DAWG_API_KEY=your_key \
  -- uv run --directory /path/to/dawg-mcp dawg-mcp
```

### Codex

Add to `~/.codex/config.toml` (see `examples/codex_config.toml`):

```toml
[mcp_servers.dawg]
command = "uvx"
args = ["dawg-mcp"]

[mcp_servers.dawg.env]
DAWG_API_KEY = "your_key"
DAWG_BASE_URL = "https://dawgswarm.ru"
```

## Configuration

| Env var | Required | Default | Description |
|---|---|---|---|
| `DAWG_API_KEY` | **yes** | — | Your DAWG API key |
| `DAWG_BASE_URL` | no | `https://dawgswarm.ru` | Platform base URL |
| `DAWG_PROVISION_TIMEOUT` | no | `120` | Max seconds to wait for a browser to be ready |
| `DAWG_POLL_INTERVAL` | no | `2` | Seconds between readiness polls |
| `DAWG_DEFAULT_NAV_TIMEOUT_MS` | no | `30000` | Default navigation timeout |
| `DAWG_DEFAULT_ACTION_TIMEOUT_MS` | no | `15000` | Default action timeout |
| `DAWG_SNAPSHOT_MAX_CHARS` | no | `60000` | Truncate snapshot/content output |
| `DAWG_MAX_SESSIONS` | no | `4` | Max concurrent browsers |
| `DAWG_LOG_LEVEL` | no | `INFO` | Log level (logs go to stderr) |

## Tools

### Browser — lifecycle
| Tool | Description |
|---|---|
| `browser_provision(proxy?, geo?)` | Provision a remote stealth Chromium. `geo` = city slug (`"moskva"`) or `"lat,lon"`. Returns `session_id` + initial snapshot. |
| `browser_release(session_id?)` | Release a browser back to the pool. |
| `browser_list_sessions()` | List active sessions. |

### Browser — driving
All take an optional `session_id` (defaults to the sole active session) and return a fresh AI
snapshot after acting. Target elements by `ref` from the latest `browser_snapshot`.

| Tool | Description |
|---|---|
| `browser_navigate(url, timeout_ms?)` | Go to a URL. |
| `browser_navigate_back()` / `browser_navigate_forward()` | History navigation. |
| `browser_snapshot()` | **See the page** — ARIA tree with `[ref=eN]` markers. |
| `browser_click(element, ref, double?, button?)` | Click an element by `ref`. |
| `browser_type(element, ref, text, submit?, clear?)` | Type into a field by `ref`. |
| `browser_fill_form(fields)` | Fill many fields at once (`[{element, ref, value}]`). |
| `browser_select_option(element, ref, values)` | Choose `<select>` option(s). |
| `browser_hover(element, ref)` | Hover an element. |
| `browser_press_key(key)` | Press a key (`"Enter"`, `"Control+a"`, …). |
| `browser_wait_for(text?, text_gone?, time_ms?)` | Wait for text / its disappearance / a delay. |
| `browser_get_text(format?, selector?)` | Get page text or HTML. |
| `browser_take_screenshot(full_page?, ref?)` | PNG image (visual verification only). |
| `browser_evaluate(function, ref?)` | Run JS, return JSON result. |
| `browser_tabs(action, index?, url?)` | `list` / `new` / `select` / `close` tabs. |

### Scraper
| Tool | Description |
|---|---|
| `scrape_page(url, format?, main_content?, include_links?, render?, timeout_ms?)` | Scrape one URL → content. |
| `scrape_crawl(url, max_depth?, max_pages?, …)` | Start a crawl job → `job_id`. |
| `scrape_batch(urls, concurrency?, …)` | Start a batch job → `job_id`. |
| `scrape_job_status(job_id, wait?, wait_timeout?)` | Poll a crawl/batch job. |
| `scrape_cancel_job(job_id)` | Cancel a job. |

### Account
| Tool | Description |
|---|---|
| `account_usage()` | Current usage and tariff plan. |

## Typical agent flow

```
browser_provision()                         → session_id + snapshot
browser_navigate(url="https://...")          → snapshot with [ref=eN] markers
browser_click(element="Login", ref="e12")    → fresh snapshot
browser_type(element="Email", ref="e8", text="...", submit=true)
browser_take_screenshot()                    → PNG to confirm visually
browser_release()
```

If a `ref` is stale (the page changed), the tool returns an error **with a fresh snapshot
appended** so the agent can re-select.

## Development

```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest            # 21 unit/integration tests (no network)
uv run ruff check .

# Live end-to-end smoke test (needs a real key):
DAWG_API_KEY=... uv run python examples/smoke_test.py

# Inspect over stdio with the MCP Inspector:
DAWG_API_KEY=... npx @modelcontextprotocol/inspector uv run dawg-mcp
```

## License

MIT — see [LICENSE](LICENSE).
