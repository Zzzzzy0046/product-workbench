---
name: overseas-consumer-app-lifecycle
description: Orchestrate overseas consumer-app product work from opportunity assessment through competitor evidence, product definition, PRD, prototype handoff, tracking, QA, and development acceptance. Use for complete new-product workflows, resuming an existing product project, or routing a scoped product task to the correct deliverable and specialist skill. Excludes paid acquisition and app-store publishing execution.
---

# Overseas Consumer App Lifecycle

## Purpose

Act as the lifecycle controller. Identify the current stage, recover the project state, retrieve relevant knowledge, select the next deliverable, invoke only the necessary specialist capability, enforce gates, and leave a reviewable handoff.

Do not copy specialist-skill instructions into this controller. Do not expand a local request into the full lifecycle unless the user asks for a full workflow.

## Scope

Covered: market and user opportunity, competitor evidence, positioning, MVP, flows, monetisation design, platform-policy constraints, technical spikes, metrics, PRD, prototype handoff, tracking, QA, and development acceptance.

Excluded: paid acquisition, media buying, campaign attribution, ASO copy, store assets, Google Play/App Store submission, staged store rollout, release notes, and store rollback.

Google Play and App Store policy checks remain in scope when they constrain product capabilities, permissions, privacy, subscriptions, ads, or data behaviour.

## Mode selection

- **Full new product:** begin at opportunity unless reliable current-project artifacts prove a later stage is ready.
- **Resume existing project:** read the current Manifest and artifacts; continue from the earliest unresolved dependency.
- **Scoped task:** produce only the requested artifact or review. List upstream gaps without automatically producing upstream documents.
- **Existing-product diagnosis:** use only when real product data already exists; do not assume store publication or launch work.

## Required opening sequence

1. Read all user-provided inputs and the current project Manifest if present.
2. Apply Source of Truth priority: current user confirmation, current source/prototype/real behaviour, current confirmed document, historical knowledge, generic template.
3. Use `product-knowledge-rag` or the Product KB MCP to retrieve relevant methods, decisions, templates, risks, and similar cases.
4. Determine mode, current state, target artifact, applicable Gate, missing evidence, and the smallest safe next action.
5. State the routing decision briefly, then execute without asking about non-blocking gaps.

If RAG is unavailable, disclose that and continue from current project evidence. Do not fabricate historical retrieval.

## State machine

```text
INITIALIZATION
  → OPPORTUNITY
  → EVIDENCE
  → DEFINITION
  → SOLUTION
  → BUILD
  → IMPLEMENTATION_ACCEPTANCE
  → ACCEPTED_HANDOFF
  → PRODUCT_OBSERVATION only when real data already exists
  → CONTINUE / ITERATE / HOLD / RETIRE
```

Read [references/artifact-router.md](references/artifact-router.md) to choose A0–A7 and specialist skills. Read [references/gates.md](references/gates.md) before issuing a Gate result. Read [references/manifest-contract.md](references/manifest-contract.md) when creating, resuming, or handing off a project.

## Gate behaviour

Do not treat a checklist as proof. A Gate decision must include outcome, evidence, unresolved gaps, owner, return stage, and next minimum action. Allowed outcomes are `Go`, `Conditional Go`, `Hold`, and `Stop`; development acceptance uses `Accepted`, `Conditional`, or `Rejected`.

Direction failure comes before feature writing. Solution failure comes before high-fidelity prototype work. Static inspection cannot pass a device gate, and a local Mock cannot prove a live API or analytics implementation.

## Evidence and platform rules

- Label facts, inferences, assumptions, decisions, risks, and non-blocking unknowns.
- Current market, competitor, price, policy, platform, regulation, and SDK facts require live verification.
- Keep shared product logic once; split Android/Google Play and iOS/App Store only where platform behaviour differs.
- Default to Android-first and iOS-secondary only as an initial assumption; reconsider by user, region, device, payment, system capability, policy, and available resources.
- Preserve source links, dates, regions, platforms, definitions, and evidence levels.

## Closing sequence

1. Update or create A0 Manifest with artifact status, Source of Truth, Gate result, blockers, and next action.
2. Verify that delivered files exist and match the claimed evidence level.
3. Stop at `ACCEPTED_HANDOFF` unless real product data is already in scope.
4. If reusable knowledge emerged, prepare a candidate summary. Do not write it into formal Product KB or Notion without explicit user authorisation.
