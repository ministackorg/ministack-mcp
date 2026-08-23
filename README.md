# ministack-mcp

<!-- mcp-name: io.github.ministackorg/ministack-mcp -->


**Your local AWS runtime for AI agents.** A Model Context Protocol server that
lets any IDE-resident AI agent (Claude Desktop, Cursor, Continue, Devin,
Cline, …) act against a local [MiniStack](https://ministack.org) environment —
deploy code, create infrastructure, run AWS CLI commands, run smoke tests,
export live state as IaC — *and* answer deterministic, version-pinned questions
about MiniStack's emulated services, supported operations, config vars, and
parity status.

The knowledge side is backed by `catalog.json` + `parity.json`, generated once
at build time from the MiniStack codebase, so those answers are stable, fast,
and tied to the exact MiniStack version you have running. The action side talks
to the live emulator at `MINISTACK_ENDPOINT_URL`.

You say "test my Lambda." The agent reads your code, deploys it, invokes it, and
tells you if it works. You say "apply my Terraform." The agent runs it against
the local environment and shows you what happened. You never think about
MiniStack — you think about your code.

- **Developer:** "Test my Lambda function" → deploys it locally, invokes it, reports pass/fail
- **Tester:** "Run my test suite" → spins up infrastructure, runs tests, cleans up
- **SRE:** "Apply my Terraform" → applies it locally, verifies resources, reports status

## Install

```bash
pipx install ministack-mcp
# or
uvx ministack-mcp
```

Set `MINISTACK_ENDPOINT_URL` (default `http://localhost:4566`) if you run
MiniStack on a non-default port.

## Tools exposed

Around 40 tools, grouped by what they do:

**Knowledge (from `catalog.json` / `parity.json`)** — `list_services`,
`get_service`, `is_operation_supported`, `search_operations`, `list_config_vars`,
`get_config_var`, `get_endpoint_info`, `find_service_for_use_case`,
`compare_with_aws`.

**State & health** — `ministack_version`, `ministack_health`, `ministack_reset`,
`reset_and_verify`, `validate_endpoint`, `get_setup_status`, `get_docker_status`.

**Act on the live emulator** — `aws_execute` (any AWS CLI command),
`create_resource`, `delete_resource`, `list_resources`, `describe_resource`,
`invoke_lambda`, `put_s3_object`, `query_dynamodb`, `send_sqs_message`,
`publish_sns`.

**Test & generate** — `run_smoke_test`, `check_terraform_coverage`,
`check_sdk_coverage`, `generate_test_fixture`, `scaffold_architecture`,
`export_setup`, `diff_environments`, `explain_error`, `suggest_next_steps`.

**Docs (also exposed as `ministack://docs/*` MCP resources)** — `get_readme`,
`get_quickstart`, `get_docker_doc`, `get_terraform_doc`, `get_testing_doc`,
`get_faq_doc`, `get_migration_guide`.

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

### Devin

Devin adds MCP servers from its web UI, not a local config file:

1. Go to **Settings → Connections → MCP servers** and click **Add a custom MCP**
   (requires the *Manage MCP Servers* permission).
2. Choose the **STDIO** transport and set **Command** `uvx` and **Args**
   `ministack-mcp`. Add `MINISTACK_ENDPOINT_URL` to the environment if you run
   MiniStack on a non-default port.

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

## Codex configuration

Codex uses the same local MCP contract as the other agents in this repo.
Keep `MINISTACK_ENDPOINT_URL` pointed at the MiniStack instance you want to use.

### Codex CLI

Register the server with the local `uvx` entry point:

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

If you need a non-default backend:

```bash
export MINISTACK_ENDPOINT_URL=http://localhost:4566
uvx ministack-mcp
```

### Codex app

Use the same MCP server definition in the Codex app settings:

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

If the app exposes a separate MCP settings screen, add the same `command` and
`args` pair there.

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
5. `server.py` reads both files at import time and exposes the tools above
   over MCP stdio. The knowledge tools answer from the catalog; the action
   tools (`aws_execute`, `invoke_lambda`, `create_resource`, …) talk to the
   live emulator at `MINISTACK_ENDPOINT_URL`.

## License

MIT.
