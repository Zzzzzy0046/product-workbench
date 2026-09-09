# Artifact and skill router

| Need | Artifact | Primary specialist capability | Exit condition |
|---|---|---|---|
| Recover project state | A0 Project Manifest | lifecycle controller | stage, source, blockers, next action known |
| Produce a complete assigned-product analysis | T1 New Product Analysis (0–12) | `overseas-consumer-app-workflow` | complete market-to-execution document with positioning, MVP, risks, validation conditions and T2 entry requirements |
| Judge a new opportunity only (exception) | A1 Opportunity Brief | lifecycle controller / `overseas-consumer-app-workflow` | G1 result with evidence and kill criteria; use only when explicitly requested |
| Collect competitor review evidence | A2 input / review evidence batch | local `竞品信号工坊` for raw Google Play / App Store reviews | raw reviews, metadata, batch scope and limitations saved |
| Understand competitors | A2 Competitor Evidence Pack | `competitor-analysis`; local review collector; `android-app-screenshot` for authorised device inspection | evidence produces explicit product implications |
| Define positioning and MVP | A3 Product Definition | product strategy, monetisation, pricing, prioritisation skills as needed | G2 result and bounded MVP |
| Produce the product framework and version plan | T2 Product Framework / Version Plan | `product-strategy`, `prioritize-features`, `tech-architect` as needed | product structure, MVP/V0/V1 boundaries, priorities and dependencies are explicit |
| Specify business rules | A4 PRD | `prd-prototype-standard` for full package; `prototype-requirement-writer` for scoped pages | states, exceptions, AC, privacy and dependencies closed |
| Hand off experience | A5 Prototype Handoff | prototype/design capability matching the requested source | pages map to A4 and include required states |
| Produce the page-level PRD and prototype handoff | T3 PRD / Prototype Handoff | `prd-prototype-standard`, `prototype-requirement-writer`, relevant prototype capability | page IDs, states, rules, copy, annotations and traceability are reviewable |
| Track risk and decisions | A6 Risk & Decision Log | lifecycle controller; `pre-mortem` when requested or high-risk | owners, evidence, revisit triggers recorded |
| Measure and accept | A7 Tracking / QA / Acceptance Pack | `tracking-spec-from-prototype`, `tracking-implementation-validator`, `qa-engineer` | G4 result backed by matching implementation evidence |
| Produce the measurement, QA and acceptance pack | T4 Tracking / QA / Acceptance | `tracking-spec-from-prototype`, `tracking-implementation-validator`, `qa-engineer` | metrics, events, test evidence, residual risks and acceptance result are complete |

## Routing rules

- Canonical names are `A0 Project Manifest` and `A1 Opportunity Brief`; older inventories that used A0/A1 for different documents are historical aliases, not the current contract. Prefer immutable template IDs when resolving ambiguity.
- For an assigned-product request, T1 is the primary user-facing deliverable. A1 is not required and is only created when the user explicitly asks for opportunity screening.
- T1–T4 are the canonical user-facing deliverable templates. A0–A7 remain the control, evidence and handoff records; use both layers when the project needs traceability.
- G1 is not part of the default assigned-product flow. Evidence gaps become assumptions, validation tasks, scope constraints, or later-stage kill criteria. A `Hold` or `Stop` at G1 applies only when the user explicitly requested opportunity screening.
- The local review collector is optional and only runs when review evidence is needed and app identifiers/markets are available. Keep DeepSeek and external translation off by default; its output is current-project evidence, not formal Product KB content.
- A one-page or grammar request remains scoped.
- “根据 PRD 生成友盟埋点表” routes to `tracking-spec-from-prototype`, not analytics-query tools.
- Store screenshots do not substitute for authorised device experience.
- A located file is not an edited, exported, or validated artifact.
- Use current project components and templates before historical ones.
- Call `lead-review` before a major PRD/prototype/acceptance handoff when the deliverable warrants a formal final review.
