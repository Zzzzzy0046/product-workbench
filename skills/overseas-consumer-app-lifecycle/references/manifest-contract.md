# A0 Project Manifest contract

The Manifest is the handoff interface among users, agents, stages, and specialist skills. It is not a project essay.

Required fields:

- project identity and one-sentence direction;
- target platform and candidate regions;
- workflow mode and current state;
- latest Gate result;
- current Source of Truth paths and versions;
- A1–A7 artifact paths, statuses, versions, and owners;
- evidence level of each claimed validation;
- open assumptions, decisions, risks, blockers, and conflicts;
- conflicts between historical next actions and the current authorised scope;
- next minimum action;
- last updated time.

Artifact status values: `Missing`, `Draft`, `Review`, `Accepted`, `Superseded`, `Blocked`, `Not Applicable`.

On resume, verify referenced files still exist and have not been replaced before trusting status. On close, update only facts within the current task scope; do not mark later stages complete by inference.

When a historical action conflicts with the current user-authorised scope, record the conflict in A0 and mark that action `Not Applicable` or `Deferred`. Do not place it in the execution queue.

The canonical template is Product KB knowledge ID `template-a0-project-manifest`.
