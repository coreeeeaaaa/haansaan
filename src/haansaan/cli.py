from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from haansaan.core import (
    build_agent_call_error_response,
    build_agent_call_response,
    build_judgment,
    build_possibility_certificate,
    build_route_decision,
    dumps_json,
    list_entry_labels,
    list_profiles,
    list_tools,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="haansaan", description="Purpose-driven verifier judgment router")
    subparsers = parser.add_subparsers(dest="command", required=True)

    judge = subparsers.add_parser("judge", help="Select and optionally run purpose-relevant verifier adapters")
    judge.add_argument("--purpose", default="")
    judge.add_argument("--profile", action="append", default=[], help="Purpose profile id such as math, code, memory, quality")
    judge.add_argument("--target", action="append", default=[])
    judge.add_argument("--criteria", action="append", default=[])
    judge.add_argument("--mode", choices=["plan", "check", "run"], default="check")
    judge.add_argument("--tool", action="append", default=[], help="Force include a tool id")
    judge.add_argument("--input-text", default="")
    judge.add_argument("--output-text", default="")
    judge.add_argument("--context-text", default="")
    judge.add_argument("--claim", action="append", default=[])
    judge.add_argument("--evidence-ref", action="append", default=[])
    judge.add_argument("--memory-ref", action="append", default=[])
    judge.add_argument("--flow-step", action="append", default=[])
    judge.add_argument("--artifact-path", action="append", default=[])
    judge.add_argument("--next-action", action="append", default=[])
    judge.add_argument("--resource-profile-json", default="", help="Optional JSON object with bounded resource evidence")
    judge.add_argument("--architecture-note", default="")
    judge.add_argument("--risk-item", action="append", default=[])
    judge.add_argument("--attack-scenario", action="append", default=[])
    judge.add_argument("--review-scope", default="")
    judge.add_argument("--maintenance-note", default="")
    judge.add_argument("--innovation-claim", action="append", default=[])
    judge.add_argument("--json", action="store_true")

    decide = subparsers.add_parser("decide", help="Classify a target and emit a verifier route decision without executing probes")
    decide.add_argument("--target-text", required=True)
    decide.add_argument("--purpose", default="")
    decide.add_argument("--target", action="append", default=[])
    decide.add_argument("--constraint", action="append", default=[])
    decide.add_argument("--input-text", default="")
    decide.add_argument("--output-text", default="")
    decide.add_argument("--context-text", default="")
    decide.add_argument("--claim", action="append", default=[])
    decide.add_argument("--evidence-ref", action="append", default=[])
    decide.add_argument("--memory-ref", action="append", default=[])
    decide.add_argument("--flow-step", action="append", default=[])
    decide.add_argument("--artifact-path", action="append", default=[])
    decide.add_argument("--next-action", action="append", default=[])
    decide.add_argument("--resource-profile-json", default="", help="Optional JSON object with bounded resource evidence")
    decide.add_argument("--architecture-note", default="")
    decide.add_argument("--risk-item", action="append", default=[])
    decide.add_argument("--attack-scenario", action="append", default=[])
    decide.add_argument("--review-scope", default="")
    decide.add_argument("--maintenance-note", default="")
    decide.add_argument("--innovation-claim", action="append", default=[])
    decide.add_argument("--json", action="store_true")

    call = subparsers.add_parser("call", help="External program JSON call contract for agents")
    call.add_argument("--request", default="", help="JSON request file. If omitted, stdin is read.")
    call.add_argument("--pretty", action="store_true", help="Pretty-print JSON response")

    tools = subparsers.add_parser("tools", help="List registered adapters")
    tools.add_argument("--check", action="store_true", help="Check local availability")
    tools.add_argument("--json", action="store_true")

    profiles = subparsers.add_parser("profiles", help="List purpose profiles")
    profiles.add_argument("--json", action="store_true")

    labels = subparsers.add_parser("labels", help="List stable entry labels")
    labels.add_argument("--json", action="store_true")

    possibility = subparsers.add_parser("possibility", help="Emit a non-circular certificate rejecting absolute completion impossibility")
    possibility.add_argument("--json", action="store_true")
    possibility.add_argument("--out", default="", help="Optional path to write the certificate JSON artifact")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "judge":
        artifacts = _judge_artifacts(args)
        payload = build_judgment(
            purpose=args.purpose,
            target_kinds=tuple(args.target),
            criteria_tags=tuple(args.criteria),
            mode=args.mode,
            allow_tools=tuple(args.tool),
            profiles=tuple(args.profile),
            artifacts=artifacts,
        )
        _emit(payload, json_output=args.json)
        return 1 if payload["fail_count"] else 0
    if args.command == "decide":
        artifacts = _judge_artifacts(args)
        payload = build_route_decision(
            target_text=args.target_text,
            purpose=args.purpose,
            target_kinds=tuple(args.target),
            constraints=tuple(args.constraint),
            artifacts=artifacts,
        )
        _emit(payload, json_output=args.json)
        return 0
    if args.command == "call":
        payload, exit_code = _cmd_call(args)
        if args.pretty:
            print(dumps_json(payload))
        else:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return exit_code
    if args.command == "tools":
        payload = list_tools(check_availability=args.check)
        _emit(payload, json_output=args.json)
        return 0
    if args.command == "profiles":
        payload = list_profiles()
        _emit(payload, json_output=args.json)
        return 0
    if args.command == "labels":
        payload = list_entry_labels()
        _emit(payload, json_output=args.json)
        return 0
    if args.command == "possibility":
        payload = build_possibility_certificate()
        if args.out:
            Path(args.out).write_text(dumps_json(payload) + "\n", encoding="utf-8")
        _emit(payload, json_output=args.json)
        return 0 if payload["modal_judgment"]["diamond_p"] else 1
    parser.error("unknown command")
    return 2


def _judge_artifacts(args: argparse.Namespace) -> dict:
    artifacts = {
        "input_text": args.input_text,
        "output_text": args.output_text,
        "context_text": args.context_text,
        "claims": args.claim,
        "evidence_refs": args.evidence_ref,
        "memory_refs": args.memory_ref,
        "flow_steps": args.flow_step,
        "artifact_paths": args.artifact_path,
        "next_actions": args.next_action,
        "architecture_notes": args.architecture_note,
        "risk_items": args.risk_item,
        "attack_scenarios": args.attack_scenario,
        "review_scope": args.review_scope,
        "maintenance_notes": args.maintenance_note,
        "innovation_claims": args.innovation_claim,
    }
    if args.resource_profile_json:
        resource_profile = json.loads(args.resource_profile_json)
        if not isinstance(resource_profile, dict):
            raise ValueError("HAANSAAN_RESOURCE_PROFILE_JSON_MUST_BE_OBJECT")
        artifacts["resource_profile"] = resource_profile
    return {key: value for key, value in artifacts.items() if value}


def _cmd_call(args: argparse.Namespace) -> tuple[dict, int]:
    try:
        raw = Path(args.request).read_text(encoding="utf-8") if args.request else sys.stdin.read()
        request = json.loads(raw)
        response = build_agent_call_response(request)
    except Exception as exc:
        return (
            build_agent_call_error_response(
                reason_code="HAANSAAN_AGENT_CALL_INVALID_REQUEST",
                error_summary=str(exc),
            ),
            2,
        )
    fail_count = int(response.get("judgment", {}).get("fail_count") or 0)
    return response, 1 if fail_count else 0


def _emit(payload: dict, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    print(dumps_json(payload))


if __name__ == "__main__":
    raise SystemExit(main())
