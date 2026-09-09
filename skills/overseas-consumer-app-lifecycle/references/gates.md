# Gate definitions

## G1 Opportunity Gate（仅在明确要求机会评估时使用）

This is not a default blocking Gate for a product category assigned by the user. Use it only when the user explicitly asks whether an idea is worth doing, wants to screen multiple ideas, or asks to stop before product definition.

Required: specific beachhead user and situation, credible problem cost, reason to start now, first-value moment, natural repeat path, plausible monetisation fit, major policy/technical risk, and falsifiable validation threshold.

For the default assigned-product flow, record these as T1 assumptions, risks, research questions and validation thresholds, then continue to G2 Definition Gate.

## G2 Definition Gate

Required: competitor and user evidence translated into positioning, perceivable differentiation, product boundary, bounded MVP, retention logic, monetisation logic, platform decision, and explicit no-build list.

## G3 Solution Gate

Required: end-to-end main flow, loading/empty/fail/timeout/permission/interruption/restore states, business rules, free/paid boundary, permissions and privacy, technical spike results or owners, acceptance criteria, and traceability among A3–A6.

## G4 Development Acceptance Gate

Required: core value path on target device/build, PRD-prototype-implementation consistency, tracking event/parameter/timing match, subscription/ad/permission behaviour, exception recovery, crash/performance/compatibility checks, and a closed list of residual issues.

PASS without a screenshot is acceptable for event validation when the captured event, parameters, values, and timing match. FAIL includes necessary evidence. BLOCKED and NOT_RUN state the reason and never count as PASS.

## G5 Iteration Gate

Use only when real product data exists. Diagnose activation, retention, monetisation, quality, and guardrails before choosing Continue, Iterate, Hold, or Retire. Arithmetic correctness does not prove analytics taxonomy or deterministic user attribution.

## Decision record

Every Gate result contains:

- outcome and one-sentence rationale;
- passed evidence with source and level;
- failed or conditional items;
- owner and due condition;
- return stage;
- next minimum action;
- kill or revisit trigger.
