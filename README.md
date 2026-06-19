# ministack-mcp

<!-- mcp-name: io.github.ministackorg/ministack-mcp -->

**Your local AWS runtime.** An MCP server that gives any AI agent (Claude,
Cursor, Continue, Windsurf, Cline) a full AWS environment on localhost.
The agent deploys your code, creates infrastructure, runs tests, and
reports results — all locally, instantly, free.

You say "test my Lambda." The agent reads your code, deploys it, invokes
it, and tells you if it works. You say "apply my Terraform." The agent
runs it against the local environment and shows you what happened. You
never think about MiniStack. You think about your code.

## Install

```bash
pipx install ministack-mcp
# or
uvx ministack-mcp
```

## What happens

The MCP tells your AI agent: "You have a local AWS environment. Use it."

- **Developer:** "Test my Lambda function" → agent deploys it locally, invokes it, reports pass/fail
- **Tester:** "Run my test suite" → agent spins up infrastructure, runs tests, cleans up
- **SRE:** "Apply my Terraform" → agent applies it locally, verifies resources, reports status

The agent uses 38 tools to act on your behalf. MiniStack runs 67 AWS services locally.

## IDE configuration

### Claude Desktop / Claude Code

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

### Continue / Windsurf / Cline

Same pattern — `"command": "uvx", "args": ["ministack-mcp"]` in your MCP config.

Set `MINISTACK_ENDPOINT_URL` if not using the default `http://localhost:4566`.

## License

MIT.
