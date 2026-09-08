# Knowledge governance

## Status

- `draft`: not yet trusted for default retrieval.
- `active`: current formal knowledge.
- `superseded`: preserved for history but excluded from normal retrieval.
- `archived`: retained but no longer operational.

## Evidence levels

From weaker to stronger: unverified, inference, source-backed, project-validated, real-data-validated. File existence, static inspection, local Mock, build success, device behaviour, and live API/data are separate evidence layers.

## Freshness

Check `reviewed_at` and `expires_at`. Current market, competitor, price, platform policy, SDK capability, and regulation claims must be refreshed rather than repeated from old knowledge.

## Conflicts

Do not delete a conflicting historical result. Record both IDs, their dates and evidence, then resolve through source authority. When a new decision replaces an old one, mark the old item `superseded` and set an explicit relationship.

## Candidate write-back

A candidate must contain:

- one reusable conclusion;
- applicable and non-applicable conditions;
- original source and date;
- evidence level;
- relationship to existing knowledge;
- proposed status;
- confirmation that sensitive data is absent;
- explicit user authorisation.
