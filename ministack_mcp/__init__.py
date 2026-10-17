"""MiniStack MCP — knowledge layer for AI agents."""


def main() -> None:
    from ministack_mcp.server import main as _main

    _main()


__all__ = ["main"]
