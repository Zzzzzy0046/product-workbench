# Retrieval contract

## `kb_search`

Inputs:

- `query`: one concrete product question.
- `top_k`: normally 5–10.
- optional `product`, `stage`, `platform`, `region`, `domain`, `knowledge_type`.

Each result includes adjusted score, raw retrieval score, immutable chunk ID, source ID, title, locator, text, type, status, evidence level, review date, and available scope metadata.

Use filters only when the value is known. An incorrect filter is worse than no filter. If a filtered query returns too little, remove the least certain filter once and retry.

For one scoped decision, normally run no more than two distinct searches and one widened retry. Select only the 3–6 results that could change scope, risk, commercialisation, or the Gate; do not call `kb_get` for every search hit.

## `kb_get`

Use the immutable `chunk_id` returned by search. Fetch before relying on a truncated or high-impact result.

## `kb_trace`

Input `source_id`. It returns the source path, current fingerprint, metadata, and indexed locators. Use it for important claims and version conflicts.

## `kb_find_similar_cases`

Searches only `type: case`. Use it for analogy, failure patterns, template evolution, and comparable product boundaries. A case is supportive evidence, not proof that the same decision applies now.

## Default call budget

- `kb_search`: 2 decision queries plus 1 widened retry.
- `kb_find_similar_cases`: 1 call.
- `kb_get`: up to 6 selected chunks.
- `kb_trace`: up to 4 decision-critical sources.

An explicit knowledge audit may exceed the budget. A normal product task may exceed it only to resolve a concrete conflict found by the initial retrieval, and the final context block must state why.

## Query examples

- “Android 健康类新品首次价值和政策风险”
- “已有 PRD 和当前原型冲突时 Source of Truth”
- “Reader-first 文件产品的 MVP 边界”
- “埋点 PASS FAIL BLOCKED 的研发验收规则”
