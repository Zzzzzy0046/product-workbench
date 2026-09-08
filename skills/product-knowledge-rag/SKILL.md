---
name: product-knowledge-rag
description: Retrieve traceable product methods, decisions, templates, risks, and prior cases from the local Product KB before or during overseas consumer-app work. Use when a task should reuse historical product knowledge, resolve conflicting versions, choose a prior template, or cite the source behind a recommendation. Do not use for unrelated self-contained questions.
---

# Product Knowledge RAG

## Outcome

Bring only the most relevant, current, source-traceable knowledge into the task. Retrieval informs the current decision; it never overrides current user confirmation or current project evidence.

The Product KB MCP is read-only. Expected tools are `kb_search`, `kb_get`, `kb_trace`, and `kb_find_similar_cases`.

## Retrieval workflow

1. Identify the current product, task, workflow stage, platform, region, and knowledge domain. Unknown fields may remain unset.
2. Form one decision-oriented query. Search for the product question, not the user’s entire prompt.
3. Call `kb_search` with the narrowest reliable metadata filters. Start with `top_k=8`; widen once only if the result is insufficient.
4. For project analogies, call `kb_find_similar_cases` separately. Do not treat a similar case as a rule.
5. Use `kb_get` for any result that materially changes scope, policy, commercialisation, permissions, metrics, or acceptance.
6. Use `kb_trace` to verify the original path, fingerprint, date, and locator before presenting a retrieved claim as source-backed.
7. Return a compact context block: reused knowledge, current applicability, conflicts or staleness, and source IDs.

Read [references/retrieval-contract.md](references/retrieval-contract.md) when composing tool calls or interpreting results. Read [references/governance.md](references/governance.md) when results conflict, may be stale, or could be written back.

## Source authority

Apply this order:

`current user confirmation > current source/prototype/real behaviour > confirmed current-project document > dated historical knowledge > generic template`

Retrieved text is not automatically true for the current project. Preserve its product, platform, region, evidence level, status, and review date. Policy, price, market, platform capability, and competitor facts require live verification when current accuracy matters.

## Output discipline

- Separate `[事实]`, `[推断]`, `[假设]`, `[决策]`, and `[风险]`.
- Cite source IDs next to reused conclusions.
- State when a result is a historical pattern rather than current evidence.
- If two active results conflict, show both and identify what evidence or user decision resolves them.
- Do not flood the task with raw chunks. Prefer structured methods, decisions, patterns, templates, and cases; use raw sources for evidence traceability.

## Write boundary

Never write directly to formal knowledge through this skill. Do not treat ordinary task completion as permission to archive knowledge.

When reusable knowledge emerges, prepare a candidate only if useful. It remains outside the formal index until the user explicitly asks to “沉淀”, “归档”, or “保存到知识库”. Notion synchronisation requires separate explicit authorisation.

Never retain credentials, cookies, tokens, private account data, raw sensitive company metrics, or noisy intermediate analysis.

## Fallback

If the Product KB MCP is unavailable, say that RAG retrieval was not executed. If the Product KB root is explicitly available, a read-only local text search may be used as a labelled fallback; do not claim it is hybrid retrieval and do not search unrelated user directories.
