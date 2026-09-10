---
name: overseas-consumer-app-lifecycle
description: "Orchestrate overseas consumer-app work for small fast-moving teams through complete Heart Rate-style new-product analysis, a core PRD, and development acceptance. Use formal gates and research only when explicitly requested."
---

# Overseas Consumer App Lifecycle

## Purpose

Route an assigned consumer-App category through the smallest useful set of Chinese deliverables. The default is not a formal stage-gate process.

```text
Current direction + supplied evidence
  → F1 New Product Analysis
  → F2 Core PRD
  → F3 Development Acceptance Checklist
```

Paid acquisition, media buying, attribution, ASO copy, store assets and store publishing are out of scope. Fast F1 does not contain a platform, permissions, data or policy section; concrete permission interactions belong in the relevant F2 page only when required.

## Mode selection

- **Fast path by default:** read [references/fast-iteration-path.md](references/fast-iteration-path.md). Use for an assigned category, a small team, competitor-led development or a quick iteration request.
- **Formal full path only by explicit request:** use historical T1–T4 and formal gates only for a requested 0–12 research package, formal investment review or broad cross-team handoff.
- **Scoped task:** produce only the requested artifact. Do not expand a PRD or review request into the lifecycle.
- **Existing product:** use real behaviour and data when supplied; do not invent launch or store state.

“完整新品分析” still uses the fast F1 when the user also says small team, quick iteration or competitor-led development. It means a complete usable analysis, not automatically a 0–12 chapter report.

## Opening sequence

1. Read current user direction and all explicitly selected project materials.
2. Apply Source of Truth priority: current user confirmation, current source/prototype/real behaviour, accepted project document, historical knowledge, generic template.
3. Retrieve only relevant Product KB methods/templates when available.
4. Choose F1, F2 or F3 and execute the smallest useful next deliverable.

Do not block on an undefined target user or missing user interviews. Describe likely users from the product direction, competitor use cases and supplied evidence. Do not create a research programme unless asked.

## Evidence inputs

Competitor review CSV, policy sources, technical logs, screenshots and research documents are working inputs and must enter the deliverable when selected:

- list them in the document evidence index;
- explain the material finding and where it changes the product, PRD or acceptance result;
- pass screenshots as visual input and describe relevant UI/state details;
- preserve links, filenames and dates;
- summarize relevant content instead of pasting raw files.

Fast mode does not use `[fact]`, `[inference]`, `[assumption]`, `[risk]` or validation labels. It also does not create risk registers, user interview plans, technical Spike documents, Gates or condition-closure tasks. Ordinary implementation uncertainty belongs in “Engineering confirmation”; actual defects belong in F3.

## Canonical fast deliverables

- F1: `knowledge/templates/f1-new-product-analysis.md` — complete Heart Rate-style product analysis with evidence, competitor differences, product framework, core modules, flows and monetisation.
- F2: `knowledge/templates/f2-core-prd.md` — only the pages, rules, states and acceptance needed for the current build.
- F3: `knowledge/templates/f3-development-acceptance.md` — one living checklist for planned and actual results.

Read [references/artifact-router.md](references/artifact-router.md) for routing. Read [references/gates.md](references/gates.md) only when the user explicitly requests a formal gate. Read [references/manifest-contract.md](references/manifest-contract.md) when resuming or handing off a saved project.

When real competitor reviews are required, read [references/competitor-review-collector.md](references/competitor-review-collector.md). The local collector acquires raw reviews only; ordinary F1 directly analyzes an uploaded CSV.

## Handoff

1. Verify the current deliverable exists and stays within its scope and length budget.
2. Ensure every selected source appears in the evidence index and is used near the relevant conclusion.
3. Keep accepted upstream documents as references instead of repeating their content.
4. Stop after the requested deliverable. Do not auto-generate later documents.
5. Do not write to Product KB, Notion or GitHub without explicit authorization.
