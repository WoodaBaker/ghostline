"""Ghostline MCP server — thin wrapper over the battery registry.

Exposes probe/report as MCP tools so any MCP-capable assistant can run
diagnostics conversationally ("check my agent for goal drift").

Requires the `mcp` extra: pip install kiru-ghostline[mcp]
Staged after the standalone package works (kiru#509).
"""

TOOLS = ["probe_disorder", "finding_report"]


def build_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        raise RuntimeError("pip install kiru-ghostline[mcp] to run the MCP server")

    from .batteries import get as get_battery
    from .findings import Finding
    from .runner import resolve_target, run_batteries

    server = FastMCP("ghostline")

    @server.tool()
    def probe_disorder(target: str, disorders: list[str] | None = None, max_calls: int = 200) -> dict:
        """Run Ghostline probe batteries against a target agent."""
        report = run_batteries(resolve_target(target), slugs=disorders, max_calls=max_calls)
        return report.to_dict()

    @server.tool()
    def finding_report(behavior: str, model: str = "", scaffolding: str = "") -> dict:
        """Document a behavioral finding in the kiru upload-ready format."""
        return Finding(
            observed_behavior=behavior, model=model, scaffolding=scaffolding
        ).to_dict()

    return server


def main():
    build_server().run()


if __name__ == "__main__":
    main()
