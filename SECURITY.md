# Security Policy

## Scope

This repository contains the public `haansaan` verifier judgment router.
It must not contain private workspace paths, private project names, secrets,
credentials, model keys, local logs, cache files, or unpublished internal
planning material.

## Boundary

`haansaan` is not a truth oracle, proof engine, autonomous agent, sandbox, or
security scanner by itself. It routes bounded requests to selected built-in or
external adapters and records machine-readable `PASS`, `REPORT`, or `FAIL`
rows.

Optional external tools such as Semgrep, Bandit, pip-audit, Pyright, Ruff,
Radon, and cloc are separate dependencies. A missing or failing external tool
must remain `REPORT` or `FAIL`; it must not be promoted to `PASS`.

## Public Release Gate

Before publishing or tagging a release, run:

```bash
python3 -B -m pytest tests -q -p no:cacheprovider
ruff check .
gitleaks detect --source . --no-git --redact --verbose
detect-secrets scan .
```

If Semgrep, Bandit, pip-audit, or Pyright are part of a release claim, their
local results must also be captured. Tool installation alone is not release
evidence.

## Reporting

Report suspected vulnerabilities privately to the repository owner. Do not put
secrets, tokens, private paths, or exploit payloads in public issues.
