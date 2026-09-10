# Artifact and skill router

| Need | Artifact | Primary capability | Exit condition |
|---|---|---|---|
| Turn an assigned category and materials into a product direction | F1 New Product Analysis | `overseas-consumer-app-workflow` | evidence, competitor difference, positioning, V0 and flow are usable |
| Specify the current build | F2 Core PRD | `prototype-requirement-writer` or relevant prototype capability | pages, rules, states and acceptance are ready for design/development |
| Plan and record development acceptance | F3 Development Acceptance Checklist | `tracking-spec-from-prototype` and `qa-engineer` only when needed | expected and actual results point to logs/screenshots/retest evidence |
| Collect raw competitor reviews | F1 evidence input | local `竞品信号工坊` | CSV and collection scope are saved |
| Produce a formal 0–12 research package | Full T1–T4 | `overseas-consumer-app-workflow` formal mode | only when explicitly requested |
| Resume a saved project | A0 Project Manifest | lifecycle controller | current artifacts, sources and next action are known |

## Routing rules

- An assigned-product request defaults to F1 → F2 → F3.
- Comments, policy sources, logs, screenshots and research documents are inputs to these deliverables, not separate mandatory reports.
- Ordinary fast work does not create opportunity briefs, risk logs, technical Spikes, conditions or Gates.
- A large comment dataset may use a separate comment-analysis task, but its result must still be selected into F1.
- F2 references F1 instead of repeating market, user and competitor background.
- F3 is updated in place; do not split planned and actual acceptance into two default documents.
- A grammar, copy, single-page PRD or review request remains scoped.
- “根据 PRD 生成友盟埋点表” routes to `tracking-spec-from-prototype`.
- Store screenshots are competitor evidence; they do not prove real device behaviour.
