# Artifact and skill router

| Need | Artifact | Primary capability | Exit condition |
|---|---|---|---|
| Analyze an assigned category or supplied competitor candidates | F1 five chapters / scoped competitor note | current F1 templates and project evidence | user can select references and use supported product decisions |
| Prepare the current module for external prototype work | flow/pages, shared rules if needed, prototype handoff | available prototype capability only when actual execution is requested | page form, hierarchy, copy, actions and stable IDs are clear |
| Revise real review comments or check consistency | review-changes / consistency-review | current baselines and real comments | replacement text and exact outstanding sync locations are clear |
| Need an independent development document | optional F2 Core PRD | current page requirements | reuse the same confirmed page text; only add changes, no second rule set |
| Design analytics for current pages | optional complete tracking specification | `tracking-spec-from-prototype` when available | existing workbook and public events are preserved; events answer actual questions |
| Define product-facing expected cases | product-acceptance | current confirmed requirements | three columns: scenario, steps, expected; preserve existing IDs |
| Record actual build results | optional F3 | QA capability when needed | reuse expected cases and event IDs, add actual evidence and retest only |
| Collect raw competitor reviews | F1 evidence input | local `竞品信号工坊` | CSV and collection scope are saved |
| Produce a formal 0–12 research package | Full T1–T4 | `overseas-consumer-app-workflow` formal mode | only when explicitly requested |
| Resume a saved project | existing project context and artifacts | current scoped workflow | current stage, sources, decisions and next action are known; A0 only for explicit formal mode |

## Routing rules

- Default navigation is analysis → page-first prototype requirements → review changes → final consistency → handoff. Start at the current stage; F2, tracking and real-build F3 are optional.
- Comments, policy sources, logs, screenshots and research documents are inputs to these deliverables, not separate mandatory reports.
- Ordinary fast work does not create opportunity briefs, risk logs, technical Spikes, conditions or Gates.
- A large comment dataset may use a separate comment-analysis task, but its result must still be selected into F1.
- F2 references F1 and reuses the confirmed page-note body instead of repeating analysis or freely rewriting page rules.
- When product acceptance cases exist, F3 reuses their IDs, steps and expectations. Tracking design remains in its own scheme; actual logs/status live in F3 only.
- A grammar, copy, single-page PRD or review request remains scoped.
- “根据 PRD 生成友盟埋点表” routes to `tracking-spec-from-prototype`.
- Store screenshots are competitor evidence; they do not prove real device behaviour.
