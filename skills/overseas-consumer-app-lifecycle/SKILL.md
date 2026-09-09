---
name: overseas-consumer-app-lifecycle
description: Orchestrate overseas consumer-app product work from assigned-product intake through competitor evidence, product definition, PRD, prototype handoff, tracking, QA, and development acceptance. Use for complete new-product workflows, resuming an existing product project, or routing a scoped product task to the correct deliverable and specialist skill. Opportunity screening is optional. Excludes paid acquisition and app-store publishing execution.
---

# Overseas Consumer App Lifecycle

## Purpose

Act as the lifecycle controller. Identify the current stage, recover the project state, retrieve relevant knowledge, select the next deliverable, invoke only the necessary specialist capability, enforce gates, and leave a reviewable handoff.

The user-facing default is **deliverable-first**. For a product category explicitly assigned by the user, the primary output is the complete T1 New Product Analysis (0–12 chapters), followed by T2 when the user continues. A0–A7 are control and handoff artifacts that support the main deliverable and may be kept concise or internal unless the user asks to inspect them. The workflow does not re-litigate whether the category should exist.

Do not copy specialist-skill instructions into this controller. Do not expand a local request into the full lifecycle unless the user asks for a full workflow.

## Scope

Covered: market and user opportunity, competitor evidence, positioning, MVP, flows, monetisation design, platform-policy constraints, technical spikes, metrics, PRD, prototype handoff, tracking, QA, and development acceptance.

Excluded: paid acquisition, media buying, campaign attribution, ASO copy, store assets, Google Play/App Store submission, staged store rollout, release notes, and store rollback.

Google Play and App Store policy checks remain in scope when they constrain product capabilities, permissions, privacy, subscriptions, ads, or data behaviour.

## Mode selection

- **Assigned product (default):** route to `overseas-consumer-app-workflow` and produce the complete T1 New Product Analysis using the historical 0–12 structure. Treat the product category as approved for analysis and execution planning. Record weak evidence as assumptions, risks, validation tasks, scope reductions, or later-stage rejection criteria; do not use a G1 Opportunity Gate to block the workflow.
- **Opportunity-only evaluation (exception):** produce A1 Opportunity Brief and G1 only when the user explicitly asks to judge an opportunity, screen ideas, or decide whether to research further.
- **Resume existing project:** read the current Manifest and artifacts; continue from the earliest unresolved dependency.
- **Scoped task:** produce only the requested artifact or review. List upstream gaps without automatically producing upstream documents.
- **Existing-product diagnosis:** use only when real product data already exists; do not assume store publication or launch work.

## Required opening sequence

1. Read all user-provided inputs and the current project Manifest if present.
2. Apply Source of Truth priority: current user confirmation, current source/prototype/real behaviour, current confirmed document, historical knowledge, generic template.
3. Use `product-knowledge-rag` or the Product KB MCP to retrieve relevant methods, decisions, templates, risks, and similar cases.
4. Determine mode, current state, target artifact, applicable Gate, missing evidence, and the smallest safe next action. For an assigned product, skip G1 by default and target `T1 New Product Analysis` unless the user explicitly requested a later artifact.
5. State the routing decision briefly, then execute without asking about non-blocking gaps.

If RAG is unavailable, disclose that and continue from current project evidence. Do not fabricate historical retrieval.

## State machine

```text
INITIALIZATION
  → EVIDENCE
  → DEFINITION
  → SOLUTION
  → BUILD
  → IMPLEMENTATION_ACCEPTANCE
  → ACCEPTED_HANDOFF
  → PRODUCT_OBSERVATION only when real data already exists
  → CONTINUE / ITERATE / HOLD / RETIRE
```

The state machine controls evidence and handoff; it does not decide whether a user-assigned category is worth doing. `OPPORTUNITY` may remain as a historical label for source material, but it is not a default blocking Gate. A full T1 ends with an execution recommendation, scope, risks, validation conditions, and the entry requirements for T2.

Read [references/artifact-router.md](references/artifact-router.md) to choose A0–A7 and specialist skills. Read [references/gates.md](references/gates.md) before issuing a Gate result. Read [references/manifest-contract.md](references/manifest-contract.md) when creating, resuming, or handing off a project.
When T1/A2 needs real competitor review evidence, read [references/competitor-review-collector.md](references/competitor-review-collector.md) and use the local collector only for raw review acquisition and verification.

## Canonical product deliverables

The Product KB is the canonical template source for the four user-facing deliverables:

- T1: `knowledge/templates/t1-new-product-analysis.md` — complete Chinese 0–12 new-product analysis;
- T2: `knowledge/templates/t2-product-framework-version-plan.md` — product framework and version plan;
- T3: `knowledge/templates/t3-prd-prototype-handoff.md` — page-level PRD and prototype handoff;
- T4: `knowledge/templates/t4-tracking-qa-acceptance.md` — tracking, QA and development acceptance.

Use A0–A7 for state, evidence, Gate, risk and traceability. Formal outputs are Chinese by default; retain English only for necessary technical identifiers and UI copy. Do not expand the workflow into paid acquisition, media buying, attribution, ASO, store assets or store publishing execution.

## Gate behaviour

Do not treat a checklist as proof. A Gate decision must include outcome, evidence, unresolved gaps, owner, return stage, and next minimum action. For the default assigned-product flow, the first blocking Gate is G2 Definition Gate. G1 remains available only for an explicitly requested opportunity evaluation. Development acceptance uses `Accepted`, `Conditional`, or `Rejected`.

For full T1 delivery, weak direction or missing evidence is recorded as scope, risk, validation work, or a later kill criterion; it is not a reason to block the assigned category at G1. Solution failure comes before high-fidelity prototype work. Static inspection cannot pass a device gate, and a local Mock cannot prove a live API or analytics implementation.

## Evidence and platform rules

- Label facts, inferences, assumptions, decisions, risks, and non-blocking unknowns.
- Current market, competitor, price, policy, platform, regulation, and SDK facts require live verification.
- Keep shared product logic once; split Android/Google Play and iOS/App Store only where platform behaviour differs.
- Default to Android-first and iOS-secondary only as an initial assumption; reconsider by user, region, device, payment, system capability, policy, and available resources.
- Preserve source links, dates, regions, platforms, definitions, and evidence levels.

## Deliverable-first routing

Use this default routing for a new product:

```text
User direction + existing evidence
  ↓
Product KB / historical template retrieval
  ↓
Optional competitor review collection (raw reviews only)
  ↓
T1 New Product Analysis (0–12)
  ├─ A0 state record (concise)
  ├─ A2 competitor evidence summary
  └─ A3/MVP recommendation
  ↓ only after explicit continuation
T2 Product Framework / Version Plan
  ↓ only after explicit continuation
T3 PRD / Prototype Handoff
  ↓ only after explicit continuation
T4 Tracking / QA / Acceptance
```

Do not expose the user to a controller-only response such as `A0 → A1 → Hold` when the request is for an assigned product. The correct response is a complete T1 with an execution recommendation and the next T2 entry conditions. Use `A1 → G1` only when the user explicitly requests opportunity screening.

## Closing sequence

1. Update or create A0 Manifest with artifact status, Source of Truth, Gate result, blockers, and next action.
2. Verify that the primary user-facing deliverable exists and matches the claimed evidence level. For a full new-product request, this is the complete T1 document.
3. Stop after the requested deliverable and Gate result. Do not generate T2/T3/T4 unless the user asks to continue or the task explicitly requests the full downstream lifecycle.
4. If reusable knowledge emerged, prepare a candidate summary. Do not write it into formal Product KB or Notion without explicit user authorisation.
