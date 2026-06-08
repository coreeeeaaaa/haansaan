# Publication Boundary

`haansaan` may be public only as a bounded verifier judgment router.

## Allowed

- Public source code for the router, CLI, schemas, tests, and examples.
- Generic examples that use repo-relative paths.
- Neutral descriptions of supported profiles and adapters.
- Evidence that local tests and configured scans ran.

## Not Allowed

- Private workspace names or absolute local paths.
- Private project names, private memory references, credentials, API keys, or
  local logs.
- Claims that `haansaan` proves truth, completes arbitrary work, replaces
  mature security tools, or guarantees release readiness.
- Cached files such as `__pycache__`, `.pytest_cache`, local virtual
  environments, build output, or scan output with private paths.

## Release Claim Rule

A release claim is valid only for the exact checks that ran. Missing tools,
missing artifacts, weak evidence, or failed probes must remain `REPORT` or
`FAIL`.

`PASS` means bounded local evidence exists for the selected row. It does not
mean the reviewed artifact is globally correct, secure, complete, or ready for
publication.
