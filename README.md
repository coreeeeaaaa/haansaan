# haansaan

`haansaan` is an independent verifier judgment system.

It does not pretend to prove, score, or complete a claim by itself. It takes a
purpose, target kind, and criteria, selects the relevant existing verifier
adapters, checks whether they are available, and optionally runs only selected
safe probes.

It is built for subprocess use by agents. The caller passes a purpose, one or
more purpose profiles, and bounded artifacts. `haansaan` routes to the relevant
adapters instead of running every check at once.

Missing tools, missing artifacts, unavailable probes, and weak evidence do not
end as a stop-only blocker. They produce machine-readable `REPORT` rows with:

- `understanding`
- `analysis`
- `depth_measure`
- `improvement_points`
- `direction`
- `possible_worlds`
- `judgment`
- `next_actions`

`REPORT` is not `PASS`; it is the decision surface for the next action.

Every request also receives stable entry labels before adapter selection. These
labels are the trust surface for reentry, comparison, and downstream routing.
They are deterministic for the same input and are not completion or truth
claims.

## Documentation

- [Internal Procedure And Triggers](docs/INTERNAL_PROCEDURE_AND_TRIGGERS.md)
- [Publication Boundary](docs/PUBLICATION_BOUNDARY.md)
- [Security Policy](SECURITY.md)

## Commands

```bash
haansaan labels --json
haansaan profiles --json
haansaan possibility --json
haansaan possibility --json --out /tmp/haansaan-possibility-certificate.json
haansaan judge --profile code_review --artifact-path /path/to/file.py --mode run --json
haansaan judge --profile code_security --output-text "bounded file handling" --mode run --json
haansaan judge --profile architecture --flow-step parse --flow-step route --resource-profile-json '{"network_required":false}' --mode run --json
python3 -m haansaan.cli judge --purpose "logic constraint" --target formula --criteria satisfiability --mode check --json
python3 -m haansaan.cli judge --purpose "logic constraint" --target formula --criteria satisfiability --mode run --json
haansaan judge --profile purpose_drift --output-text "purpose direction objective preserved" --mode run --json
python3 -m haansaan.cli tools --json
printf '%s\n' '{"schema_id":"HAANSAAN_AGENT_CALL_REQUEST_V1","request_id":"r1","caller":"agent","purpose":"logic constraint","target_kinds":["formula"],"criteria_tags":["satisfiability"],"mode":"check"}' | haansaan call
haansaan call --request examples/logic-run.request.json
haansaan call --request examples/agent-workflow-review.request.json
```

Modes:

- `plan`: select tools only; no availability check and no execution.
- `check`: select tools and check local availability; no execution.
- `run`: select tools, check availability, and run only selected safe adapters.

Boundary:

- no fake data
- no arbitrary success rate
- no confidence score without real meta-analysis evidence
- no full parallel execution unless the request actually selects all tools
- no completion or release claim
- built-in gates are structural guards, not truth oracles
- unavailable capability yields a decision report, not a dead stop

Row statuses:

- `PASS`: bounded local evidence was produced.
- `REPORT`: the adapter/profile produced an actionable analysis report for next
  decision. This includes missing tools, missing request artifacts, unavailable
  safe probes, and plan/check mode selection.
- `FAIL`: an executed probe or structural gate found a concrete failure.

Entry label axes:

- `request:*`: purpose/profile/target/criteria/allow-tool request surface.
- `mode:*`: `plan`, `check`, or `run`.
- `profile:*`: purpose profile selected at ingress.
- `artifact:*`: bounded artifact fields supplied by the caller.

The label registry is available through `haansaan labels --json`.

## Possibility Certificate

`haansaan possibility --json` emits a non-circular construction certificate for
rejecting the claim that haansaan completion is absolutely impossible.
Use `--out <path>` to persist the same certificate as a replayable evidence
artifact.

The certificate does not claim current full completion or release readiness. It
shows a closed path `C` made from fixed schemas, finite registries,
deterministic selection, bounded execution modes, verdict algebra, decision
reports, and an executed construction witness.

Machine-readable modal result:

```json
{
  "schema_id": "HAANSAAN_COMPLETION_POSSIBILITY_CERTIFICATE_V1",
  "verdict": "ABSOLUTE_IMPOSSIBILITY_REJECTED",
  "modal_judgment": {
    "box_not_p": false,
    "diamond_p": true,
    "diamond_box_p_under_closed_path_c": true,
    "formula": "◇C ∧ □(C -> P)"
  },
  "srvl_boundary": {
    "current_full_completion_claim": false,
    "release_ready_claim": false
  },
  "evidence_digests": {
    "closed_path_c_sha256": "...",
    "construction_witness_sha256": "...",
    "evidence_items_sha256": "..."
  }
}
```

Use this output when the needed question is possibility/impossibility, not
current release completion.

## External Program Contract

Agents and other systems should call `haansaan call` as a subprocess and pass a
single JSON object by stdin or with `--request <file>`.

Purpose profiles:

- `math`: symbolic, numeric, matrix, optimization, and solver checks.
- `code`: syntax, lint, type, style, unit, and regression checks.
- `formal`: formal proof, model, and contract verification.
- `natural_language`: prose quality and NLP structure.
- `semantic_logic`: claim/evidence/premise/contradiction review.
- `purpose_drift`: detects surface-only output and purpose loss.
- `context`: flow, replay, step, and experience trace review.
- `memory`: source, retention, and memory contamination boundary review.
- `contamination`: public/private, secret, workspace, and context pollution guard.
- `stability`: rollback, reentry, resource, and zombie-process guard.
- `quality`: general work-product quality gate.
- `management`: completion bar, evidence trace, owner, and next-action gate.
- `io_flow`: input, output, artifact, and pipeline flow verification.
- `code_review`: code review, lint, audit, grammar, and syntax surface.
- `code_security`: code safety, security, risk, and dependency vulnerability review.
- `attack_verification`: adversarial, threat-model, attack-surface, and abuse-case verification.
- `architecture`: system structure, boundary, and architecture quality measurement.
- `complexity`: system level, difficulty, complexity, and blast-radius measurement.
- `maintainability`: maintainability, management, ownership, and change-surface review.
- `innovation`: innovation, novelty, differentiation, and practicality assessment.

Optional external adapters:

- Code review and syntax: Ruff, Pyright, Tree-sitter, Lark, ANTLR.
- Security and attack review: Semgrep, Bandit, pip-audit.
- Complexity and maintainability: Radon, cloc.

If an optional adapter is missing, `haansaan` returns a `REPORT` with the
capability gap and next action instead of pretending the check passed.

Request:

```json
{
  "schema_id": "HAANSAAN_AGENT_CALL_REQUEST_V1",
  "request_id": "stable-caller-id",
  "caller": "external-agent-name",
  "purpose": "logic constraint",
  "profiles": ["math"],
  "target_kinds": ["formula"],
  "criteria_tags": ["satisfiability"],
  "mode": "check",
  "allow_tools": [],
  "artifacts": {
    "input_text": "",
    "output_text": "",
    "context_text": "",
    "artifact_paths": [],
    "flow_steps": [],
    "memory_refs": [],
    "evidence_refs": [],
    "next_actions": [],
    "resource_profile": {},
    "architecture_notes": "",
    "risk_items": [],
    "attack_scenarios": [],
    "review_scope": "",
    "maintenance_notes": "",
    "innovation_claims": []
  }
}
```

Response:

```json
{
  "schema_id": "HAANSAAN_AGENT_CALL_RESPONSE_V1",
  "ok": true,
  "request_id": "stable-caller-id",
  "judgment": {
    "schema_id": "HAANSAAN_PURPOSE_TRIGGER_JUDGMENT_V1",
    "entry_labels": ["mode:check", "request:purpose", "request:profile", "profile:math"],
    "entry_label_report": {
      "schema_id": "HAANSAAN_ENTRY_LABEL_REPORT_V1",
      "labels_by_axis": {
        "mode": ["mode:check"],
        "profile": ["profile:math"],
        "request": ["request:purpose", "request:profile"]
      }
    },
    "selected_tool_ids": ["z3", "cvc5"],
    "pass_count": 0,
    "report_count": 2,
    "fail_count": 0,
    "decision_report": {
      "schema_id": "HAANSAAN_AGGREGATE_DECISION_REPORT_V1",
      "judgment": "REPORT_ONLY_NEXT_ACTION_REQUIRED",
      "next_actions": []
    }
  }
}
```

Exit codes:

- `0`: valid request; no selected probe failed.
- `1`: valid request; at least one selected executed probe failed.
- `2`: invalid request or invalid JSON.
