# Internal Procedure And Triggers

This document describes how `haansaan` receives a request, labels it, selects
purpose-relevant verifier adapters, runs bounded checks, and emits a judgment.

`haansaan` is a verifier judgment router. It is not a truth oracle, autonomous
agent, sandbox, proof engine, or security scanner by itself.

The highest-level entry is route decision. A caller can ask `haansaan` to
classify the target and recommend which review, proof, security, synthesis, or
quality path should be considered before any verifier execution.

## System Surfaces

`haansaan` has four public surfaces:

1. CLI commands for humans and local scripts.
2. A JSON subprocess contract for agents and external programs.
3. Finite registries for profiles, labels, adapters, and probes.
4. Machine-readable judgment reports with `PASS`, `REPORT`, and `FAIL` rows.

The implementation entrypoints are:

- `haansaan decide`: target classification and route decision without probe
  execution.
- `haansaan judge`: direct CLI judgment route.
- `haansaan call`: external program JSON call contract.
- `haansaan tools`: registered adapter inventory.
- `haansaan profiles`: purpose profile inventory.
- `haansaan labels`: stable entry label inventory.
- `haansaan possibility`: bounded construction certificate for rejecting
  absolute impossibility claims.

## Request Contract

External callers use `HAANSAAN_AGENT_CALL_REQUEST_V1`.

Required:

- `schema_id`: must be `HAANSAAN_AGENT_CALL_REQUEST_V1`.
- `request_id`: caller-stable id for trace and replay.
- `caller`: external caller label.
- `purpose`: human-readable purpose string.
- `mode`: `plan`, `check`, or `run`.

Optional:

- `profiles`: purpose profile ids.
- `target_kinds`: target labels such as `code`, `report`, `formula`, `package`.
- `criteria_tags`: requested criteria such as `satisfiability`, `lint`,
  `secret_leak`, or `purpose_preservation`.
- `allow_tools`: explicit adapter ids to force include.
- `artifacts`: bounded input/output/context/paths/evidence fields.

The response uses `HAANSAAN_AGENT_CALL_RESPONSE_V1` and wraps a
`HAANSAAN_PURPOSE_TRIGGER_JUDGMENT_V1` judgment.

For route selection, callers set `"operation": "decide"` and provide
`target_text`, optional `purpose`, optional `target_kinds`, optional
`constraints`, and bounded `artifacts`. The response still uses
`HAANSAAN_AGENT_CALL_RESPONSE_V1`, but wraps
`HAANSAAN_TARGET_ROUTE_DECISION_V1` under `route_decision`.

## Route Decision Flow

Use this flow when the caller needs to know what should inspect the target.

1. Parse target intake
   - `target_text`, purpose, target labels, constraints, and bounded artifacts
     are gathered.
   - Missing or thin intake remains `INTAKE_REQUIRED`.

2. Classify target
   - The target is assigned one or more classes:
     - `claim_review`
     - `meta_synthesis`
     - `formal_or_math`
     - `code_artifact`
     - `security_risk`
     - `architecture_system`
     - `memory_context_flow`
     - `language_surface`
     - `quality_management`
     - `io_flow`
     - `attack_surface`

3. Build required evidence map
   - Each target class receives required evidence rows.
   - Each row records `required`, `satisfied`, `missing`, and `status`.
   - Missing evidence stays `MISSING_EVIDENCE`; it is not converted to `PASS`.

4. Recommend systems
   - `claim_review` can recommend `oreo`.
   - `meta_synthesis` can recommend `yeosoooo`.
   - `formal_or_math` can recommend `z3`, `cvc5`, `lean4`, and `dafny`.
   - `code_artifact` can recommend `ruff`, `pyright`, and `haansaan`.
   - `security_risk` can recommend `semgrep`, `bandit`, `pip_audit`, and
     `haansaan`.
   - architecture, memory, language, quality, I/O, and attack-surface routes
     can recommend bounded `haansaan` profiles.

5. Emit decision-only packet
   - The route packet sets `run_policy` to `DO_NOT_AUTO_RUN`.
   - Each recommendation sets `run_now` to `false`.
   - The execution boundary sets `automatic_execution` to `false`.
   - The caller must confirm or select the next route before calling
     `haansaan judge`.

Route decision verdicts:

- `INTAKE_REQUIRED`: the target is too thin to route safely.
- `ROUTE_DESIGN_REQUIRED`: route classes were found, but required evidence is
  missing.
- `ROUTE_READY_FOR_CONFIRMATION`: the route has enough evidence for the caller
  to confirm a selected run path.

Route decision is not a proof, release claim, security approval, or maturity
claim. It is the execution-before-judgment boundary.

## Trigger Flow

The runtime follows this procedure:

1. Parse request
   - CLI args or JSON stdin/file are parsed.
   - Invalid JSON or invalid request shape exits with code `2`.

2. Normalize purpose inputs
   - Purpose text, profile ids, target kinds, criteria tags, and allowed tools
     are normalized into finite routing inputs.

3. Expand profiles
   - Each selected profile contributes purpose terms, target kinds, and
     criteria tags.
   - Unknown profile ids fail request validation instead of silently routing.

4. Build entry labels
   - Request labels record what the caller supplied.
   - Mode labels record execution depth.
   - Profile labels record selected purpose lanes.
   - Artifact labels record which bounded artifacts were supplied.

5. Select adapters
   - Each adapter is scored by purpose-axis match, criteria-tag match,
     target-kind match, and explicit allow-list match.
   - Only selected adapters are checked or run.
   - `haansaan` does not run every registered tool unless the request selects
     every registered tool.

6. Apply mode
   - `plan`: select adapters only.
   - `check`: select adapters and inspect local availability.
   - `run`: select adapters, inspect availability, and run only bounded safe
     probes or built-in probes.

7. Produce row verdicts
   - Each selected adapter yields one row.
   - Row verdict is `PASS`, `REPORT`, or `FAIL`.

8. Produce aggregate judgment
   - Any `FAIL` row makes the aggregate judgment repair-required.
   - Mixed `PASS` and `REPORT` rows produce a mixed evidence/report judgment.
   - `REPORT` only means next action is required.
   - `PASS` only means bounded evidence exists for the selected rows.

9. Emit machine-readable output
   - CLI emits JSON when `--json` is used.
   - `haansaan call` always emits JSON and returns exit codes for programmatic
     handling.

## Modes

`plan` is for routing only.

- No availability check.
- No external command execution.
- Every selected row remains a decision report.

`check` is for capability inspection.

- Checks whether selected commands/modules are available.
- Does not execute safe probes.
- Missing tools return `REPORT`.

`run` is for bounded execution.

- Executes only selected adapters.
- Executes only adapters with safe noninteractive probes or built-in probes.
- Missing capability returns `REPORT`.
- Unsafe or unimplemented probe returns `REPORT`.
- Executed probe failure returns `FAIL`.

## Profiles

Purpose profiles are coarse lanes. They route work; they do not prove that the
work is correct.

Current profile lanes:

- `math`: symbolic, numeric, matrix, optimization, and solver checks.
- `code`: syntax, lint, type, style, unit, and regression checks.
- `formal`: formal proof, model, and contract verification.
- `natural_language`: prose quality and NLP structure.
- `semantic_logic`: claim, premise, evidence, and contradiction review.
- `purpose_drift`: surface-only success and purpose loss detection.
- `context`: flow, replay, step, and experience trace review.
- `memory`: memory source, retention, and contamination boundary review.
- `contamination`: public/private, secret, workspace, and context pollution.
- `stability`: rollback, reentry, resource, and process stability review.
- `quality`: general work-product quality gate.
- `management`: completion bar, evidence trace, owner, and next action.
- `io_flow`: input, output, artifact, and pipeline flow verification.
- `code_review`: code review, lint, audit, grammar, and syntax surface.
- `code_security`: code safety, security, risk, and dependency vulnerability.
- `attack_verification`: attack-surface, threat-model, and abuse-case review.
- `architecture`: system structure, boundary, and architecture quality.
- `complexity`: level, difficulty, complexity, and blast radius.
- `maintainability`: ownership, documentation, change surface, and maintenance.
- `innovation`: novelty, differentiation, and practicality.

## Adapter Kinds

Adapters are finite registry entries.

- `builtin`: local structural probes implemented inside `haansaan`.
- `python_module`: Python import based tools such as Z3, SymPy, NumPy, or
  scikit-learn.
- `command`: local executable tools such as CVC5, Lean, Ruff, Semgrep, Bandit,
  pip-audit, Radon, or cloc.
- `local_system`: local named systems that may exist outside this package.

Adapter availability is evidence about the local environment. It is not
evidence that the target artifact is correct.

## Built-In Probes

Built-in probes provide structural reports for routing and next-action
selection. They intentionally avoid pretending to be complete external tools.

Built-in lanes include:

- artifact I/O boundary
- semantic logic boundary
- purpose drift boundary
- context and flow trace boundary
- memory boundary
- contamination guard
- stability guard
- quality and management verification
- code review surface
- code safety and security risk
- adversarial attack verification
- system architecture quality
- complexity and difficulty level
- maintainability
- innovation and novelty assessment

Built-in `PASS` means the supplied bounded artifacts met that structural gate.
It does not mean global truth, security, or release readiness.

## Row Verdicts

`PASS`

- Bounded local evidence was produced for the selected row.
- The evidence is scoped to the selected adapter and supplied artifacts.

`REPORT`

- The row produced actionable analysis but not enough evidence for `PASS`.
- This covers missing tools, missing input artifacts, unavailable probes,
  unimplemented safe probes, and plan/check-mode routing.

`FAIL`

- An executed probe or built-in structural gate found a concrete failure.
- The caller should repair the failed path and rerun the same profile.

## Decision Report Fields

Each row and aggregate report can include:

- `understanding`: what was selected and why.
- `analysis`: what the row found.
- `depth_measure`: bounded measurement of evidence depth.
- `improvement_points`: concrete ways to strengthen the next run.
- `direction`: decision direction for the caller.
- `possible_worlds`: next-state branches and expected effects.
- `judgment`: machine-readable decision class.
- `next_actions`: actionable next steps.
- `evidence_boundary`: non-claim fields that prevent false promotion.

`depth_measure` is not a confidence score.

## Exit Codes

`haansaan call` uses stable exit codes:

- `0`: valid request and no selected executed probe failed.
- `1`: valid request and at least one selected executed probe failed.
- `2`: invalid request, invalid JSON, or invalid request shape.

## Security Boundary

`haansaan` should be treated as a local subprocess tool.

Public-safe rules:

- Do not pass secrets or private files unless the caller intentionally wants a
  local private scan.
- Do not publish reports that include private paths, private project names,
  credentials, tokens, or internal memory references.
- Do not treat `PASS` as a publication or release claim.
- Do not treat missing external tools as success.

Implementation safety rules:

- External subprocess calls are fixed command lists, not caller-provided shell
  strings.
- Safe probes use timeouts.
- Temporary files are written under temporary directories for probe execution.
- Missing or unsafe probe capability stays `REPORT`.

## Release Boundary

The repository is suitable for source use when its public checks pass.

Minimum public source checks:

```bash
python3 -B -m pytest tests -q -p no:cacheprovider
ruff check .
gitleaks detect --source . --no-git --redact --verbose
detect-secrets scan .
```

Stronger release claims require extra evidence for the exact claim, such as
Semgrep, Bandit, pip-audit, Pyright, target-specific adapter execution, and
versioned release artifacts.

## Example Trigger

```bash
haansaan judge \
  --profile purpose_drift \
  --purpose "preserve objective and direction" \
  --output-text "objective and direction are preserved with evidence refs" \
  --evidence-ref "review-log:local" \
  --mode run \
  --json
```

Expected behavior:

1. labels include request, mode, profile, and artifact labels.
2. selected adapters include the purpose drift built-in probe.
3. output contains one or more row verdicts.
4. aggregate judgment stays scoped and does not become a truth claim.

## Non-Goals

`haansaan` does not:

- replace mature security, proof, lint, or evaluation tools.
- guarantee that a target artifact is correct.
- guarantee that a project is safe to publish.
- run unbounded full parallel checks by default.
- generate arbitrary confidence scores.
- convert missing evidence into success.
