from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from haansaan.core import (
    HAANSAAN_AGENT_CALL_RESPONSE_SCHEMA_ID,
    build_agent_call_response,
    build_judgment,
    build_possibility_certificate,
    list_entry_labels,
    list_profiles,
    list_tools,
)


def test_logic_constraint_selects_relevant_solvers_without_full_parallel_run() -> None:
    packet = build_judgment(
        purpose="logic constraint",
        target_kinds=("formula",),
        criteria_tags=("satisfiability", "counterexample"),
        mode="check",
    )

    assert {"z3", "cvc5"}.issubset(set(packet["selected_tool_ids"]))
    assert "matplotlib" not in packet["selected_tool_ids"]
    assert "plotly" not in packet["selected_tool_ids"]
    assert packet["selected_tool_count"] < packet["all_registry_tool_count"]
    assert packet["all_tools_triggered"] is False
    assert packet["judgment_boundary"]["not_always_full_parallel_execution"] is True
    assert packet["completion_claim"] is False
    assert packet["release_ready_claim"] is False


def test_target_kind_alone_does_not_trigger_unrelated_tools() -> None:
    packet = build_judgment(
        purpose="logic",
        target_kinds=("formula",),
        criteria_tags=("satisfiability",),
        mode="plan",
    )

    assert set(packet["selected_tool_ids"]) == {"z3", "cvc5"}
    assert all(row["status"] == "REPORT" for row in packet["tool_rows"])
    assert all(row["executed"] is False for row in packet["tool_rows"])
    assert all(row["decision_report"]["judgment"] == "REPORT_AVAILABLE_NEXT_ACTION_REQUIRED" for row in packet["tool_rows"])


def test_korean_aliases_select_judgment_adapters() -> None:
    packet = build_judgment(
        purpose="논리 제약 반례",
        target_kinds=("formula",),
        criteria_tags=("만족가능성",),
        mode="check",
    )

    assert {"z3", "cvc5"}.issubset(set(packet["selected_tool_ids"]))
    assert packet["judgment_boundary"]["no_arbitrary_success_rate"] is True


def test_run_mode_runs_only_selected_available_safe_probes() -> None:
    packet = build_judgment(
        purpose="logic constraint",
        target_kinds=("formula",),
        criteria_tags=("satisfiability",),
        mode="run",
    )

    assert packet["selected_tool_count"] == 2
    assert packet["completion_claim"] is False
    assert all(row["tool_id"] in {"z3", "cvc5"} for row in packet["tool_rows"])
    assert all(row["execute_requested"] is True for row in packet["tool_rows"])


def test_registry_lists_all_adapters_without_completion_claim() -> None:
    registry = list_tools(check_availability=False)

    assert registry["tool_count"] >= 30
    tool_ids = {tool["tool_id"] for tool in registry["tools"]}
    assert {"artifact_io_builtin", "purpose_drift_builtin", "memory_boundary_builtin"}.issubset(tool_ids)
    assert registry["completion_claim"] is False
    assert registry["release_ready_claim"] is False


def test_profiles_expose_purpose_entrypoints_without_completion_claim() -> None:
    registry = list_profiles()

    assert registry["profile_count"] >= 13
    profile_ids = {profile["profile_id"] for profile in registry["profiles"]}
    assert {
        "math",
        "code",
        "formal",
        "natural_language",
        "memory",
        "contamination",
        "quality",
        "management",
        "code_review",
        "code_security",
        "attack_verification",
        "architecture",
        "complexity",
        "maintainability",
        "innovation",
    }.issubset(profile_ids)
    assert registry["completion_claim"] is False
    assert registry["release_ready_claim"] is False


def test_entry_label_registry_exposes_stable_routing_labels() -> None:
    registry = list_entry_labels()

    assert registry["schema_id"] == "HAANSAAN_ENTRY_LABEL_REGISTRY_V1"
    label_ids = {label["label_id"] for label in registry["labels"]}
    assert {
        "request:purpose",
        "mode:run",
        "artifact:output_text",
        "profile:quality",
        "profile:memory",
        "profile:code_security",
        "profile:architecture",
        "profile:innovation",
    }.issubset(label_ids)
    assert registry["label_contract"]["same_input_same_labels"] is True
    assert registry["label_contract"]["labels_are_not_completion_claims"] is True


def test_judgment_entry_labels_are_generated_at_request_ingress() -> None:
    packet = build_judgment(
        purpose="quality review",
        profiles=("quality",),
        mode="run",
        artifacts={"output_text": "quality evidence", "evidence_refs": ["test:pytest"]},
    )

    assert packet["entry_label_report"]["schema_id"] == "HAANSAAN_ENTRY_LABEL_REPORT_V1"
    assert packet["entry_label_report"]["unregistered_labels"] == []
    assert {
        "request:purpose",
        "request:profile",
        "mode:run",
        "profile:quality",
        "artifact:output_text",
        "artifact:evidence_refs",
    }.issubset(set(packet["entry_labels"]))
    assert packet["decision_report"]["understanding"]["entry_labels"] == packet["entry_labels"]
    assert packet["tool_rows"][0]["decision_report"]["understanding"]["entry_labels"] == packet["entry_labels"]


def test_each_profile_selects_a_bounded_subset_not_all_tools() -> None:
    registry = list_profiles()

    for profile in registry["profiles"]:
        packet = build_judgment(purpose="", profiles=(profile["profile_id"],), mode="plan")
        assert packet["selected_tool_count"] > 0, profile["profile_id"]
        assert packet["selected_tool_count"] < packet["all_registry_tool_count"], profile["profile_id"]
        assert packet["all_tools_triggered"] is False


def test_math_profile_selects_math_adapters_but_not_quality_management() -> None:
    packet = build_judgment(
        purpose="",
        profiles=("math",),
        mode="plan",
    )

    assert {"z3", "cvc5", "sympy", "numpy", "scipy"}.issubset(set(packet["selected_tool_ids"]))
    assert "quality_management_builtin" not in packet["selected_tool_ids"]
    assert packet["all_tools_triggered"] is False


def test_code_review_profile_selects_review_surface_without_full_run() -> None:
    packet = build_judgment(
        purpose="",
        profiles=("code_review",),
        mode="plan",
    )

    assert "code_review_builtin" in packet["selected_tool_ids"]
    assert {"ruff", "pyright"}.issubset(set(packet["selected_tool_ids"]))
    assert packet["all_tools_triggered"] is False
    assert "profile:code_review" in packet["entry_labels"]


def test_code_security_profile_reports_safety_risk_surface() -> None:
    packet = build_judgment(
        purpose="",
        profiles=("code_security",),
        mode="run",
        artifacts={"output_text": "bounded file handling without dynamic execution", "risk_items": ["dependency review"]},
    )

    assert "code_safety_security_builtin" in packet["selected_tool_ids"]
    assert {"semgrep", "bandit", "pip_audit"}.issubset(set(packet["selected_tool_ids"]))
    row = next(row for row in packet["tool_rows"] if row["tool_id"] == "code_safety_security_builtin")
    assert row["status"] == "REPORT"
    assert row["reason_code"] == "CODE_SECURITY_SURFACE_REPORT"
    assert row["decision_report"]["next_actions"]


def test_architecture_complexity_maintainability_innovation_profiles_report_measurements() -> None:
    cases = {
        "architecture": "system_architecture_builtin",
        "complexity": "complexity_level_builtin",
        "maintainability": "maintainability_builtin",
        "innovation": "innovation_builtin",
    }

    for profile_id, tool_id in cases.items():
        packet = build_judgment(
            purpose="",
            profiles=(profile_id,),
            mode="run",
            artifacts={
                "architecture_notes": "module boundary interface data flow rollback runtime",
                "maintenance_notes": "owner docs dependency lock tests",
                "innovation_claims": ["new labeled decision report routing"],
                "evidence_refs": ["test:pytest"],
                "flow_steps": ["label", "select", "report"],
            },
        )
        assert tool_id in packet["selected_tool_ids"]
        if profile_id == "innovation":
            assert "sympy" not in packet["selected_tool_ids"]
        row = next(row for row in packet["tool_rows"] if row["tool_id"] == tool_id)
        assert row["status"] == "REPORT"
        assert row["decision_report"]["schema_id"] == "HAANSAAN_DECISION_REPORT_V1"
        assert row["evidence"]
        assert f"profile:{profile_id}" in packet["entry_labels"]


def test_purpose_drift_profile_runs_structural_builtin_only_when_requested() -> None:
    packet = build_judgment(
        purpose="",
        profiles=("purpose_drift",),
        mode="run",
        artifacts={"output_text": "purpose direction objective preserved"},
    )

    assert packet["selected_tool_ids"] == ["purpose_drift_builtin"]
    assert packet["pass_count"] == 1
    assert packet["report_count"] == 0
    assert packet["tool_rows"][0]["reason_code"] == "BUILTIN_STRUCTURAL_CHECK_PASS"
    assert packet["decision_report"]["judgment"] == "BOUNDED_EVIDENCE_AVAILABLE"


def test_missing_or_unavailable_tool_produces_decision_report_not_block_stop() -> None:
    packet = build_judgment(
        purpose="메타분석 신뢰도",
        target_kinds=("report",),
        criteria_tags=("bayesian_update",),
        mode="check",
    )

    assert packet["selected_tool_ids"] == ["yeosoooo"]
    assert packet["report_count"] == 1
    row = packet["tool_rows"][0]
    assert row["status"] == "REPORT"
    assert row["availability"]["status"] in {"AVAILABLE", "UNAVAILABLE"}
    assert row["decision_report"]["schema_id"] == "HAANSAAN_DECISION_REPORT_V1"
    assert row["decision_report"]["improvement_points"]
    assert row["decision_report"]["possible_worlds"]
    assert row["decision_report"]["next_actions"]
    assert packet["decision_report"]["judgment"] == "REPORT_ONLY_NEXT_ACTION_REQUIRED"


def test_agent_call_response_wraps_judgment_for_subprocess_callers() -> None:
    response = build_agent_call_response(
        {
            "schema_id": "HAANSAAN_AGENT_CALL_REQUEST_V1",
            "request_id": "case-logic-1",
            "caller": "agent",
            "purpose": "logic constraint",
            "target_kinds": ["formula"],
            "criteria_tags": ["satisfiability"],
            "mode": "plan",
        }
    )

    assert response["schema_id"] == HAANSAAN_AGENT_CALL_RESPONSE_SCHEMA_ID
    assert response["request_id"] == "case-logic-1"
    assert response["contract"]["callable_by_external_program"] is True
    assert response["contract"]["stdout_json_only"] is True
    assert response["judgment"]["selected_tool_ids"] == ["z3", "cvc5"]
    assert response["completion_claim"] is False


def test_agent_call_accepts_profiles_and_artifacts_for_purpose_specific_use() -> None:
    response = build_agent_call_response(
        {
            "schema_id": "HAANSAAN_AGENT_CALL_REQUEST_V1",
            "request_id": "case-memory-1",
            "caller": "agent",
            "purpose": "memory boundary",
            "profiles": ["memory"],
            "artifacts": {"memory_refs": ["memory:session"]},
            "mode": "run",
        }
    )

    assert response["schema_id"] == HAANSAAN_AGENT_CALL_RESPONSE_SCHEMA_ID
    assert response["judgment"]["selected_tool_ids"] == ["memory_boundary_builtin"]
    assert response["judgment"]["pass_count"] == 1
    assert response["judgment"]["fail_count"] == 0


def test_cli_call_reads_stdin_json_and_emits_machine_response() -> None:
    project_root = Path(__file__).resolve().parents[1]
    request = {
        "schema_id": "HAANSAAN_AGENT_CALL_REQUEST_V1",
        "request_id": "stdin-case",
        "caller": "pytest-agent",
        "purpose": "메타분석 신뢰도",
        "target_kinds": ["report"],
        "criteria_tags": ["bayesian_update"],
        "mode": "check",
    }
    result = subprocess.run(
        [sys.executable, "-m", "haansaan.cli", "call"],
        cwd=project_root,
        env={**os.environ, "PYTHONPATH": str(project_root / "src")},
        input=json.dumps(request, ensure_ascii=False),
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["schema_id"] == HAANSAAN_AGENT_CALL_RESPONSE_SCHEMA_ID
    assert payload["judgment"]["selected_tool_ids"] == ["yeosoooo"]
    assert payload["judgment"]["report_count"] == 1
    assert payload["judgment"]["tool_rows"][0]["reason_code"] in {"MISSING_COMMAND", "COMMAND_FOUND"}
    assert payload["judgment"]["tool_rows"][0]["decision_report"]["next_actions"]


def test_cli_profiles_lists_machine_readable_profile_registry() -> None:
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "haansaan.cli", "profiles", "--json"],
        cwd=project_root,
        env={**os.environ, "PYTHONPATH": str(project_root / "src")},
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["schema_id"] == "HAANSAAN_PURPOSE_PROFILE_REGISTRY_V1"
    assert "math" in {profile["profile_id"] for profile in payload["profiles"]}


def test_cli_labels_lists_machine_readable_entry_label_registry() -> None:
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "haansaan.cli", "labels", "--json"],
        cwd=project_root,
        env={**os.environ, "PYTHONPATH": str(project_root / "src")},
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["schema_id"] == "HAANSAAN_ENTRY_LABEL_REGISTRY_V1"
    assert "profile:math" in {label["label_id"] for label in payload["labels"]}


def test_possibility_certificate_rejects_absolute_impossibility_without_completion_claim() -> None:
    certificate = build_possibility_certificate()

    assert certificate["schema_id"] == "HAANSAAN_COMPLETION_POSSIBILITY_CERTIFICATE_V1"
    assert certificate["verdict"] == "ABSOLUTE_IMPOSSIBILITY_REJECTED"
    assert certificate["modal_judgment"]["box_not_p"] is False
    assert certificate["modal_judgment"]["diamond_p"] is True
    assert certificate["modal_judgment"]["diamond_box_p_under_closed_path_c"] is True
    assert certificate["completion_claim"] is False
    assert certificate["release_ready_claim"] is False
    assert certificate["srvl_boundary"]["current_full_completion_claim"] is False
    assert certificate["closed_path_c"]["p_is_not_a_condition"] is True
    assert all(check["status"] == "PASS" for check in certificate["non_circularity_checks"])
    assert all(item["status"] == "SATISFIED" for item in certificate["evidence_items"])
    assert len(certificate["evidence_digests"]["closed_path_c_sha256"]) == 64
    assert len(certificate["evidence_digests"]["construction_witness_sha256"]) == 64
    assert certificate["construction_witness"]["pass_count"] > 0
    assert certificate["construction_witness"]["fail_count"] == 0


def test_cli_possibility_emits_machine_readable_certificate(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    out_path = tmp_path / "haansaan-possibility-certificate.json"
    result = subprocess.run(
        [sys.executable, "-m", "haansaan.cli", "possibility", "--json", "--out", str(out_path)],
        cwd=project_root,
        env={**os.environ, "PYTHONPATH": str(project_root / "src")},
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["schema_id"] == "HAANSAAN_COMPLETION_POSSIBILITY_CERTIFICATE_V1"
    assert payload["modal_judgment"]["diamond_p"] is True
    assert payload["rejection_target"]["claim"] == "□¬P"
    assert payload["rejection_target"]["rejected"] is True
    recorded = json.loads(out_path.read_text(encoding="utf-8"))
    assert recorded["evidence_digests"] == payload["evidence_digests"]
