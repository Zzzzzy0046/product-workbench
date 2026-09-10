# A0 Project Manifest contract

The Manifest is a small handoff record, not a product essay.

## Fast-mode fields

- project identity and one-sentence direction;
- target platform, team/timebox and current work;
- selected evidence files and dates;
- F1/F2/F3 paths and statuses;
- current implementation questions or open defects;
- next action and last updated time.

Fast mode does not require assumptions, risks, Gates, conditions, evidence levels or interview status.

## Formal-mode additions

Only when the user explicitly selects the full workflow, add Gate results, formal evidence levels, open decisions, blockers, owners, due dates and condition status.

Artifact status values: `Missing`, `Draft`, `Review`, `Accepted`, `Superseded`, `Blocked`, `Not Applicable`.

On resume, verify referenced files still exist and current user confirmation has not superseded them. Current user direction and current product behaviour outrank historical next actions.
