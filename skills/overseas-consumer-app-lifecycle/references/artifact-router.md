# Artifact and skill router

| Need | Artifact | Primary specialist capability | Exit condition |
|---|---|---|---|
| Recover project state | A0 Project Manifest | lifecycle controller | stage, source, blockers, next action known |
| Produce a complete new-product analysis | T1 New Product Analysis (0–12) | `overseas-consumer-app-workflow` | complete market-to-decision document with Go / Conditional Go / Hold / Stop |
| Judge a new opportunity only | A1 Opportunity Brief | lifecycle controller / `overseas-consumer-app-workflow` | G1 result with evidence and kill criteria; use only when explicitly requested |
| Collect competitor review evidence | A2 input / review evidence batch | local `竞品信号工坊` for raw Google Play / App Store reviews | raw reviews, metadata, batch scope and limitations saved |
| Understand competitors | A2 Competitor Evidence Pack | `competitor-analysis`; local review collector; `android-app-screenshot` for authorised device inspection | evidence produces explicit product implications |
| Define positioning and MVP | A3 Product Definition | product strategy, monetisation, pricing, prioritisation skills as needed | G2 result and bounded MVP |
| Specify business rules | A4 PRD | `prd-prototype-standard` for full package; `prototype-requirement-writer` for scoped pages | states, exceptions, AC, privacy and dependencies closed |
| Hand off experience | A5 Prototype Handoff | prototype/design capability matching the requested source | pages map to A4 and include required states |
| Track risk and decisions | A6 Risk & Decision Log | lifecycle controller; `pre-mortem` when requested or high-risk | owners, evidence, revisit triggers recorded |
| Measure and accept | A7 Tracking / QA / Acceptance Pack | `tracking-spec-from-prototype`, `tracking-implementation-validator`, `qa-engineer` | G4 result backed by matching implementation evidence |

## Routing rules

- Canonical names are `A0 Project Manifest` and `A1 Opportunity Brief`; older inventories that used A0/A1 for different documents are historical aliases, not the current contract. Prefer immutable template IDs when resolving ambiguity.
- For a full new-product request, T1 is the primary user-facing deliverable. A1 is a concise Gate/control artifact or a T1 summary, not a substitute for the 0–12 document.
- A `Hold` or `Stop` at G1 ends downstream investment, but does not truncate a requested T1 analysis. The T1 document should still state the evidence, implications, kill criteria, and final decision.
- The local review collector is optional and only runs when review evidence is needed and app identifiers/markets are available. Keep DeepSeek and external translation off by default; its output is current-project evidence, not formal Product KB content.
- A one-page or grammar request remains scoped.
- “根据 PRD 生成友盟埋点表” routes to `tracking-spec-from-prototype`, not analytics-query tools.
- Store screenshots do not substitute for authorised device experience.
- A located file is not an edited, exported, or validated artifact.
- Use current project components and templates before historical ones.
- Call `lead-review` before a major PRD/prototype/acceptance handoff when the deliverable warrants a formal final review.
