# Claude Code project setup

The project root contains `.mcp.example.json`. Copy it to `.mcp.json`, replace the placeholder paths with the local clone path, and then load the local stdio server named `product-kb`. The machine-specific `.mcp.json` is ignored by Git.

1. Open Claude Code with this `product-kb` directory as the project directory.
2. Approve the project-scoped MCP server when Claude Code shows the trust prompt.
3. Run `/mcp` or `claude mcp list` and confirm `product-kb` is connected.
4. Confirm the tools `kb_search`, `kb_get`, `kb_trace`, and `kb_find_similar_cases` are present.
5. Add or import the two skill folders only after the MCP connection passes.

Do not copy credentials into `.mcp.json`. This server is local, read-only, and requires no authentication secret.
