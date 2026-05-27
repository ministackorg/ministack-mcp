# ministack-mcp

<!-- mcp-name: io.github.ministackorg/ministack-mcp -->


The **knowledge layer** for [MiniStack](https://ministack.org) — a Model Context
Protocol server that lets any IDE-resident AI agent (Claude Desktop, Cursor,
Continue, Windsurf, Cline, …) ask deterministic, version-pinned questions about
MiniStack's emulated services, supported operations, configuration vars, and
parity status.

The catalog is generated once at build time from the MiniStack codebase, so the
MCP server never re-parses code at request time. AI answers are stable, fast,
and tied to the exact MiniStack version you have running.

## Install

```bash
pipx install ministack-mcp
# or
uvx ministack-mcp
```

Set `MINISTACK_ENDPOINT_URL` (default `http://localhost:4566`) if you run
MiniStack on a non-default port.

## Tools exposed

| Tool                        | What it answers                                                |
| --------------------------- | -------------------------------------------------------------- |
| `ministack_version`         | Which MiniStack version this catalog reflects                  |
| `ministack_health`          | Live probe — is the emulator running                           |
| `ministack_reset`           | Clear in-memory state (between test scenarios)                 |
| `get_endpoint_info`         | Port, default account/region, auth model                       |
| `list_services`             | Every service + status badge + op count                        |
| `get_service`               | Full info for one service (ops, parity, gotchas, notes)        |
| `is_operation_supported`    | Definitive yes/no for a `(service, operation)` pair            |
| `search_operations`         | Substring search across every service's operation list         |
| `list_config_vars`          | Every env var MiniStack reads                                  |
| `get_config_var`            | Default + source files for one env var                         |

## IDE configuration

### Claude Desktop / Claude Code

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "ministack": {
      "command": "uvx",
      "args": ["ministack-mcp"],
      "env": {
        "MINISTACK_ENDPOINT_URL": "http://localhost:4566"
      }
    }
  }
}
```

### Cursor

`~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ministack": {
      "command": "uvx",
      "args": ["ministack-mcp"]
    }
  }
}
```

### Continue (`.continuerc` or `~/.continue/config.json`)

```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "transport": {
          "type": "stdio",
          "command": "uvx",
          "args": ["ministack-mcp"]
        }
      }
    ]
  }
}
```

### Windsurf

`~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "ministack": {
      "command": "uvx",
      "args": ["ministack-mcp"]
    }
  }
}
```

### Cline (VS Code extension)

VS Code settings, `cline.mcpServers`:

```json
{
  "ministack": {
    "command": "uvx",
    "args": ["ministack-mcp"]
  }
}
```

## Regenerating the catalog

When MiniStack itself changes, regenerate the catalog before publishing a new
release of `ministack-mcp`:

```bash
python build_catalog.py
```

This rewrites `catalog.json` in place. `parity.json` is hand-curated and is
never touched by the generator.

## How it works

1. `build_catalog.py` walks `ministack/services/*.py` and extracts AWS
   operation names from action dicts, equality compares, `match`/`case`
   blocks, URL-path dispatch dicts, and module docstrings.
2. It also walks all of `ministack/` for `os.environ.get` / `os.getenv` /
   `os.environ[...]` to inventory every env var the emulator reads.
3. The result, `catalog.json`, is shipped with the package.
4. `parity.json` adds curated status (full / partial / stub / paid /
   data-plane / unsupported), real-backend flags, persistence, and gotchas.
5. `mcp_server.py` reads both files at import time and exposes the tools
   above over MCP stdio.

## License

MIT.
