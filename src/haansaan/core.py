from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

HAANSAAN_SCHEMA_ID = "HAANSAAN_PURPOSE_TRIGGER_JUDGMENT_V1"
HAANSAAN_AGENT_CALL_REQUEST_SCHEMA_ID = "HAANSAAN_AGENT_CALL_REQUEST_V1"
HAANSAAN_AGENT_CALL_RESPONSE_SCHEMA_ID = "HAANSAAN_AGENT_CALL_RESPONSE_V1"
HAANSAAN_POSSIBILITY_CERTIFICATE_SCHEMA_ID = "HAANSAAN_COMPLETION_POSSIBILITY_CERTIFICATE_V1"
Mode = Literal["plan", "check", "run"]
AdapterKind = Literal["python_module", "command", "local_system", "builtin"]
RowStatus = Literal["PASS", "REPORT", "FAIL"]


@dataclass(frozen=True)
class ToolAdapter:
    tool_id: str
    display_name: str
    adapter_kind: AdapterKind
    purpose_axes: tuple[str, ...]
    target_kinds: tuple[str, ...]
    criteria_tags: tuple[str, ...]
    import_name: str | None = None
    command_name: str | None = None
    safe_probe: bool = False


@dataclass(frozen=True)
class PurposeProfile:
    profile_id: str
    description: str
    purpose_terms: tuple[str, ...]
    target_kinds: tuple[str, ...]
    criteria_tags: tuple[str, ...]


@dataclass(frozen=True)
class EntryLabel:
    label_id: str
    axis: str
    description: str


TOOL_REGISTRY: tuple[ToolAdapter, ...] = (
    ToolAdapter("z3", "Z3 SMT solver", "python_module", ("logic", "constraint"), ("formula", "model"), ("satisfiability", "counterexample"), import_name="z3", safe_probe=True),
    ToolAdapter("cvc5", "CVC5 SMT solver", "command", ("logic", "constraint"), ("formula", "model"), ("satisfiability", "counterexample"), command_name="cvc5", safe_probe=True),
    ToolAdapter("sympy", "SymPy", "python_module", ("math", "symbolic"), ("formula", "expression"), ("symbolic_equivalence", "derivation", "differentiation"), import_name="sympy", safe_probe=True),
    ToolAdapter("numpy", "NumPy", "python_module", ("numeric", "matrix"), ("array", "matrix", "data"), ("numeric_reproduction", "linear_algebra"), import_name="numpy", safe_probe=True),
    ToolAdapter("scipy", "SciPy", "python_module", ("numeric", "optimization"), ("optimization_problem", "data"), ("convergence", "numeric_reproduction"), import_name="scipy", safe_probe=True),
    ToolAdapter("matplotlib", "Matplotlib", "python_module", ("visualization",), ("figure", "plot"), ("figure_reproduction", "artifact_presence"), import_name="matplotlib", safe_probe=True),
    ToolAdapter("plotly", "Plotly", "python_module", ("visualization", "interactive"), ("figure", "dashboard"), ("interactive_artifact_presence",), import_name="plotly", safe_probe=True),
    ToolAdapter("sklearn", "Scikit-learn", "python_module", ("ml", "reproduction"), ("dataset", "model"), ("metric_reproduction", "cross_validation"), import_name="sklearn", safe_probe=True),
    ToolAdapter("lean4", "Lean4", "command", ("formal_proof", "formal_type_check"), ("proof", "theorem"), ("formal_proof_check", "formal_type_check"), command_name="lean", safe_probe=True),
    ToolAdapter("dafny", "Dafny", "command", ("program_contract", "verification"), ("program", "spec"), ("pre_post_condition", "invariant"), command_name="dafny", safe_probe=True),
    ToolAdapter("alloy", "Alloy", "command", ("relational_model",), ("model", "spec"), ("instance_check", "scope_check"), command_name="alloy", safe_probe=False),
    ToolAdapter("pytest", "Pytest", "python_module", ("code_test", "regression"), ("program", "package"), ("unit_test", "regression"), import_name="pytest", safe_probe=True),
    ToolAdapter("black", "Black", "python_module", ("code_style",), ("program", "package"), ("format_consistency",), import_name="black", safe_probe=True),
    ToolAdapter("yeosoooo", "yeosoooo", "local_system", ("meta_analysis", "synthesis"), ("evidence_packet", "report"), ("cross_evidence_synthesis", "bayesian_update"), command_name="yeosoooo", safe_probe=False),
    ToolAdapter("tree_sitter", "Tree-sitter", "python_module", ("surface_syntax", "code", "syntax"), ("code", "program", "grammar"), ("parse_tree", "syntax_integrity"), import_name="tree_sitter", safe_probe=False),
    ToolAdapter("lark", "Lark", "python_module", ("surface_syntax", "grammar", "parser"), ("grammar", "text", "dsl"), ("parse_tree", "grammar_parse"), import_name="lark", safe_probe=False),
    ToolAdapter("antlr4", "ANTLR4 runtime", "python_module", ("surface_syntax", "grammar", "parser"), ("grammar", "dsl", "program"), ("grammar_parse", "language_recognition"), import_name="antlr4", safe_probe=False),
    ToolAdapter("ruff", "Ruff", "command", ("code", "code_quality"), ("program", "package"), ("lint", "import_hygiene"), command_name="ruff", safe_probe=True),
    ToolAdapter("pyright", "Pyright", "command", ("code", "type_check"), ("program", "package"), ("type_check", "static_analysis"), command_name="pyright", safe_probe=True),
    ToolAdapter("semgrep", "Semgrep", "command", ("security", "code_security", "static_analysis"), ("program", "package", "code"), ("sast", "security_rule", "injection_path"), command_name="semgrep", safe_probe=True),
    ToolAdapter("bandit", "Bandit", "command", ("security", "python_security", "code_security"), ("program", "package", "code"), ("python_security", "unsafe_api", "injection_path"), command_name="bandit", safe_probe=True),
    ToolAdapter("pip_audit", "pip-audit", "command", ("dependency_security", "supply_chain", "security"), ("package", "dependency_manifest"), ("dependency_vulnerability", "supply_chain_risk"), command_name="pip-audit", safe_probe=True),
    ToolAdapter("radon", "Radon", "command", ("complexity", "maintainability"), ("program", "package", "code"), ("cyclomatic_complexity", "maintainability_index"), command_name="radon", safe_probe=True),
    ToolAdapter("cloc", "cloc", "command", ("size", "complexity"), ("program", "package", "repository"), ("size_measurement", "language_distribution"), command_name="cloc", safe_probe=True),
    ToolAdapter("languagetool", "LanguageTool", "command", ("natural_language", "language_quality"), ("text", "document"), ("grammar_quality", "style_quality"), command_name="languagetool", safe_probe=False),
    ToolAdapter("vale", "Vale", "command", ("natural_language", "language_quality"), ("text", "document", "report"), ("prose_lint", "style_quality"), command_name="vale", safe_probe=False),
    ToolAdapter("spacy", "spaCy", "python_module", ("nlp_structure", "natural_language"), ("text", "document"), ("pos_dependency", "ner", "sentence_boundary"), import_name="spacy", safe_probe=False),
    ToolAdapter("stanza", "Stanza", "python_module", ("nlp_structure", "natural_language"), ("text", "document"), ("tokenize", "pos_dependency", "ner"), import_name="stanza", safe_probe=False),
    ToolAdapter("kiwi", "Kiwi Korean tokenizer", "python_module", ("nlp_structure", "korean", "natural_language"), ("korean_text", "text"), ("morphology", "sentence_boundary"), import_name="kiwipiepy", safe_probe=False),
    ToolAdapter("artifact_io_builtin", "Artifact I/O boundary", "builtin", ("io", "artifact", "input", "output"), ("input", "output", "artifact", "file"), ("schema_validity", "file_presence", "size_boundary", "hash_trace"), safe_probe=True),
    ToolAdapter("semantic_logic_builtin", "Semantic logic boundary", "builtin", ("semantic_logic", "argument"), ("claim", "output", "report"), ("claim_evidence_alignment", "contradiction_scan", "missing_premise"), safe_probe=True),
    ToolAdapter("purpose_drift_builtin", "Purpose drift boundary", "builtin", ("purpose_drift", "purpose", "direction", "objective"), ("output", "work_product", "report"), ("purpose_preservation", "direction_preservation", "no_surface_only_pass"), safe_probe=True),
    ToolAdapter("context_trace_builtin", "Context and flow trace boundary", "builtin", ("context", "flow", "experience", "trace"), ("workflow", "pipeline", "experience"), ("traceability", "step_order", "replay_boundary"), safe_probe=True),
    ToolAdapter("memory_boundary_builtin", "Memory boundary", "builtin", ("memory",), ("memory", "ledger", "experience"), ("memory_contamination", "source_boundary", "retention_boundary"), safe_probe=True),
    ToolAdapter("contamination_guard_builtin", "Contamination guard", "builtin", ("contamination", "pollution", "privacy", "security"), ("artifact", "workspace", "memory", "output"), ("public_private_boundary", "secret_leak", "context_pollution"), safe_probe=True),
    ToolAdapter("stability_guard_builtin", "Stability guard", "builtin", ("stability", "stabilization", "runtime"), ("runtime", "service", "pipeline"), ("rollback", "reentry", "resource_boundary", "no_zombie"), safe_probe=True),
    ToolAdapter("quality_management_builtin", "Quality and management verification", "builtin", ("quality", "management", "governance"), ("task", "plan", "work_product"), ("completion_bar", "evidence_trace", "owner_next_action"), safe_probe=True),
    ToolAdapter("code_review_builtin", "Code review surface", "builtin", ("code_review", "review", "lint", "audit", "surface_syntax"), ("code", "program", "package"), ("review_scope", "lint_surface", "syntax_surface", "audit_surface"), safe_probe=True),
    ToolAdapter("code_safety_security_builtin", "Code safety and security risk", "builtin", ("code_security", "security", "safety", "risk"), ("code", "program", "package"), ("unsafe_api", "secret_leak", "injection_path", "dependency_risk"), safe_probe=True),
    ToolAdapter("adversarial_attack_builtin", "Adversarial attack verification", "builtin", ("attack_verification", "attack", "adversarial", "threat_model"), ("attack_scenario", "system", "program"), ("attack_surface", "privilege_escalation", "abuse_case", "exploit_path"), safe_probe=True),
    ToolAdapter("system_architecture_builtin", "System architecture quality", "builtin", ("architecture", "system_structure", "module_boundary"), ("system", "architecture_notes", "workflow"), ("modularity", "data_flow", "interface_boundary", "structure_quality"), safe_probe=True),
    ToolAdapter("complexity_level_builtin", "Complexity and difficulty level", "builtin", ("complexity", "difficulty", "level"), ("system", "program", "package"), ("complexity_level", "difficulty_level", "blast_radius"), safe_probe=True),
    ToolAdapter("maintainability_builtin", "Maintainability", "builtin", ("maintainability", "maintenance"), ("system", "program", "package"), ("change_surface", "documentation", "dependency_boundary", "ownership"), safe_probe=True),
    ToolAdapter("innovation_builtin", "Innovation and novelty assessment", "builtin", ("innovation", "novelty", "differentiation"), ("system", "work_product", "idea"), ("novelty", "market_differentiation", "non_derivative", "practicality"), safe_probe=True),
)

PURPOSE_PROFILES: tuple[PurposeProfile, ...] = (
    PurposeProfile("math", "Mathematical and numeric verification", ("math", "symbolic", "numeric", "matrix", "optimization", "logic", "constraint"), ("formula", "expression", "matrix", "optimization_problem", "data"), ("symbolic_equivalence", "derivation", "numeric_reproduction", "linear_algebra", "satisfiability")),
    PurposeProfile("code", "Code syntax, lint, tests, and static checks", ("code", "surface_syntax", "code_quality", "code_style", "type_check", "code_test"), ("program", "package", "code"), ("parse_tree", "lint", "type_check", "unit_test", "regression", "format_consistency")),
    PurposeProfile("formal", "Formal proof, model, and contract verification", ("formal_proof", "formal_type_check", "program_contract", "relational_model", "logic", "constraint"), ("proof", "theorem", "model", "spec", "program"), ("formal_proof_check", "formal_type_check", "pre_post_condition", "invariant", "instance_check", "satisfiability")),
    PurposeProfile("natural_language", "Natural-language grammar, style, and NLP structure", ("natural_language", "language_quality", "nlp_structure", "korean"), ("text", "document", "korean_text"), ("grammar_quality", "style_quality", "pos_dependency", "morphology", "sentence_boundary")),
    PurposeProfile("semantic_logic", "Claim, premise, evidence, and contradiction review", ("semantic_logic", "argument"), ("claim", "output", "report"), ("claim_evidence_alignment", "contradiction_scan", "missing_premise")),
    PurposeProfile("purpose_drift", "Detect surface-only success and loss of purpose or direction", ("purpose_drift", "purpose", "direction", "objective"), ("output", "work_product", "report"), ("purpose_preservation", "direction_preservation", "no_surface_only_pass")),
    PurposeProfile("context", "Context, flow, experience, and replay boundary review", ("context", "flow", "experience", "trace"), ("workflow", "pipeline", "experience"), ("traceability", "step_order", "replay_boundary")),
    PurposeProfile("memory", "Memory source, retention, and contamination boundary review", ("memory",), ("memory", "ledger", "experience"), ("memory_contamination", "source_boundary", "retention_boundary")),
    PurposeProfile("contamination", "Secret, public/private, workspace, and context pollution guard", ("contamination", "pollution", "privacy", "security"), ("artifact", "workspace", "memory", "output"), ("public_private_boundary", "secret_leak", "context_pollution")),
    PurposeProfile("stability", "Runtime stabilization, rollback, resource, and zombie-process guard", ("stability", "stabilization", "runtime"), ("runtime", "service", "pipeline"), ("rollback", "reentry", "resource_boundary", "no_zombie")),
    PurposeProfile("quality", "General work-product quality gate", ("quality", "management"), ("work_product", "report", "program", "document"), ("completion_bar", "evidence_trace")),
    PurposeProfile("management", "Task management and completion evidence verification", ("management", "governance", "quality"), ("task", "plan", "work_product"), ("completion_bar", "evidence_trace", "owner_next_action")),
    PurposeProfile("io_flow", "Input, output, artifact, and pipeline flow verification", ("io", "artifact", "input", "output", "flow", "trace"), ("input", "output", "artifact", "file", "pipeline"), ("schema_validity", "file_presence", "size_boundary", "traceability")),
    PurposeProfile("code_review", "Code review, lint, audit, grammar, and syntax surface", ("code_review", "review", "lint", "audit", "surface_syntax", "code_quality", "code_style", "type_check"), ("code", "program", "package"), ("review_scope", "lint_surface", "syntax_surface", "audit_surface", "lint", "type_check", "format_consistency")),
    PurposeProfile("code_security", "Code safety, security, risk, and dependency vulnerability review", ("code_security", "security", "safety", "risk", "dependency_security", "supply_chain"), ("code", "program", "package", "dependency_manifest"), ("unsafe_api", "secret_leak", "injection_path", "dependency_vulnerability", "supply_chain_risk")),
    PurposeProfile("attack_verification", "Adversarial, threat-model, attack-surface, and abuse-case verification", ("attack_verification", "attack", "adversarial", "threat_model"), ("attack_scenario", "system", "program"), ("attack_surface", "privilege_escalation", "abuse_case", "exploit_path")),
    PurposeProfile("architecture", "System structure, level, boundary, and architecture quality measurement", ("architecture", "system_structure", "module_boundary"), ("system", "architecture_notes", "workflow"), ("modularity", "data_flow", "interface_boundary", "structure_quality")),
    PurposeProfile("complexity", "System level, difficulty, complexity, and blast-radius measurement", ("complexity", "difficulty", "level", "size"), ("system", "program", "package", "repository"), ("complexity_level", "difficulty_level", "blast_radius", "size_measurement")),
    PurposeProfile("maintainability", "Maintainability, ownership, and change-surface review", ("maintainability", "maintenance"), ("system", "program", "package"), ("change_surface", "documentation", "dependency_boundary", "ownership")),
    PurposeProfile("innovation", "Innovation, novelty, differentiation, and practicality assessment", ("innovation", "novelty", "differentiation"), ("system", "work_product", "idea"), ("novelty", "market_differentiation", "non_derivative", "practicality")),
)

ENTRY_LABEL_REGISTRY: tuple[EntryLabel, ...] = (
    EntryLabel("request:purpose", "request", "Caller supplied an explicit purpose string"),
    EntryLabel("request:profile", "request", "Caller supplied one or more purpose profiles"),
    EntryLabel("request:target", "request", "Caller supplied one or more target kind labels"),
    EntryLabel("request:criteria", "request", "Caller supplied one or more criteria tags"),
    EntryLabel("request:allow_tool", "request", "Caller explicitly allowed or forced a tool adapter"),
    EntryLabel("mode:plan", "mode", "Select entrypoints only"),
    EntryLabel("mode:check", "mode", "Select entrypoints and inspect local capability availability"),
    EntryLabel("mode:run", "mode", "Select entrypoints and run bounded selected probes when available"),
    EntryLabel("artifact:input_text", "artifact", "Caller supplied bounded input text"),
    EntryLabel("artifact:output_text", "artifact", "Caller supplied bounded output text"),
    EntryLabel("artifact:context_text", "artifact", "Caller supplied bounded context text"),
    EntryLabel("artifact:claims", "artifact", "Caller supplied explicit claims"),
    EntryLabel("artifact:evidence_refs", "artifact", "Caller supplied evidence references"),
    EntryLabel("artifact:memory_refs", "artifact", "Caller supplied memory references"),
    EntryLabel("artifact:flow_steps", "artifact", "Caller supplied flow or replay steps"),
    EntryLabel("artifact:artifact_paths", "artifact", "Caller supplied artifact paths"),
    EntryLabel("artifact:resource_profile", "artifact", "Caller supplied bounded resource profile evidence"),
    EntryLabel("artifact:architecture_notes", "artifact", "Caller supplied architecture notes"),
    EntryLabel("artifact:risk_items", "artifact", "Caller supplied explicit risk items"),
    EntryLabel("artifact:attack_scenarios", "artifact", "Caller supplied attack scenarios"),
    EntryLabel("artifact:review_scope", "artifact", "Caller supplied review scope"),
    EntryLabel("artifact:maintenance_notes", "artifact", "Caller supplied maintenance notes"),
    EntryLabel("artifact:innovation_claims", "artifact", "Caller supplied innovation claims"),
)


TOKEN_ALIASES: dict[str, str] = {
    "논리": "logic",
    "제약": "constraint",
    "반례": "counterexample",
    "만족가능성": "satisfiability",
    "수학": "math",
    "기호": "symbolic",
    "미분": "differentiation",
    "수치": "numeric",
    "행렬": "matrix",
    "최적화": "optimization",
    "수렴": "convergence",
    "시각화": "visualization",
    "그래프": "figure",
    "그림": "figure",
    "대시보드": "dashboard",
    "머신러닝": "ml",
    "모델": "model",
    "재현": "reproduction",
    "성능": "metric_reproduction",
    "증명": "formal_proof",
    "형식증명": "formal_proof",
    "타입체크": "type_check",
    "계약": "program_contract",
    "불변식": "invariant",
    "테스트": "unit_test",
    "회귀": "regression",
    "포맷": "format_consistency",
    "메타분석": "meta_analysis",
    "종합": "synthesis",
    "신뢰도": "bayesian_update",
    "코드": "code",
    "문법": "surface_syntax",
    "표면": "surface_syntax",
    "자연어": "natural_language",
    "언어": "natural_language",
    "맥락": "context",
    "기억": "memory",
    "오염": "contamination",
    "안정화": "stabilization",
    "안정성": "stability",
    "퀄리티": "quality",
    "품질": "quality",
    "관리": "management",
    "흐름": "flow",
    "경험": "experience",
    "입력": "input",
    "출력": "output",
    "목적": "purpose",
    "방향": "direction",
    "목적상실": "purpose_drift",
    "방향상실": "purpose_drift",
    "코드리뷰": "code_review",
    "리뷰": "review",
    "린트": "lint",
    "오디팅": "audit",
    "감사": "audit",
    "안전성": "safety",
    "보안": "security",
    "리스크": "risk",
    "위험": "risk",
    "공격": "attack",
    "공격검증": "attack_verification",
    "위협모델": "threat_model",
    "구조": "architecture",
    "시스템구조": "system_structure",
    "아키텍처": "architecture",
    "레벨": "level",
    "난이도": "difficulty",
    "복잡도": "complexity",
    "복잡성": "complexity",
    "유지보수": "maintainability",
    "유지보수성": "maintainability",
    "관리성": "maintainability",
    "혁신": "innovation",
    "혁신성": "innovation",
    "새로움": "novelty",
    "차별성": "differentiation",
    "평가": "assessment",
    "측정": "measurement",
}


def list_tools(*, check_availability: bool = False) -> dict[str, Any]:
    rows = []
    for adapter in TOOL_REGISTRY:
        row = asdict(adapter)
        row["availability"] = _availability(adapter) if check_availability else {
            "status": "NOT_CHECKED",
            "reason_code": "NOT_REQUESTED",
            "path": "",
        }
        rows.append(row)
    return {
        "schema_id": "HAANSAAN_TOOL_REGISTRY_V1",
        "tool_count": len(rows),
        "tools": rows,
        "completion_claim": False,
        "release_ready_claim": False,
    }


def list_profiles() -> dict[str, Any]:
    return {
        "schema_id": "HAANSAAN_PURPOSE_PROFILE_REGISTRY_V1",
        "profile_count": len(PURPOSE_PROFILES),
        "profiles": [asdict(profile) for profile in PURPOSE_PROFILES],
        "completion_claim": False,
        "release_ready_claim": False,
    }


def list_entry_labels() -> dict[str, Any]:
    profile_labels = [
        EntryLabel(
            f"profile:{profile.profile_id}",
            "profile",
            profile.description,
        )
        for profile in PURPOSE_PROFILES
    ]
    rows = [asdict(label) for label in (*ENTRY_LABEL_REGISTRY, *profile_labels)]
    return {
        "schema_id": "HAANSAAN_ENTRY_LABEL_REGISTRY_V1",
        "label_count": len(rows),
        "labels": rows,
        "label_contract": {
            "stable_ids": True,
            "same_input_same_labels": True,
            "labels_are_not_completion_claims": True,
            "labels_route_analysis_not_truth": True,
        },
        "completion_claim": False,
        "release_ready_claim": False,
    }


def build_possibility_certificate() -> dict[str, Any]:
    witness = build_judgment(
        purpose="purpose direction objective trace",
        profiles=("purpose_drift",),
        mode="run",
        artifacts={
            "output_text": "purpose direction objective trace preserved",
            "evidence_refs": ["builtin:purpose_drift_fixture"],
            "flow_steps": ["label", "select_profile", "run_builtin", "emit_report"],
            "resource_profile": {
                "network_required": False,
                "bounded_adapter_count": 1,
                "unbounded_full_parallel_execution": False,
            },
        },
    )
    closed_path = _closed_completion_path()
    non_circular = _non_circularity_checks(closed_path=closed_path, witness=witness)
    evidence_items = _possibility_evidence_items(witness=witness)
    diamond_p = all(item["status"] == "SATISFIED" for item in evidence_items)
    diamond_box_p = diamond_p and all(check["status"] == "PASS" for check in non_circular)
    evidence_digests = {
        "closed_path_c_sha256": _sha256_json(closed_path),
        "construction_witness_sha256": _sha256_json(witness),
        "evidence_items_sha256": _sha256_json(evidence_items),
    }
    return {
        "schema_id": HAANSAAN_POSSIBILITY_CERTIFICATE_SCHEMA_ID,
        "subject": "haansaan",
        "proposition_p": "haansaan can be completed as a bounded verifier judgment router under closed internal path C",
        "verdict": "ABSOLUTE_IMPOSSIBILITY_REJECTED" if diamond_p else "ABSOLUTE_IMPOSSIBILITY_NOT_REJECTED",
        "modal_judgment": {
            "box_not_p": False if diamond_p else None,
            "diamond_p": diamond_p,
            "diamond_box_p_under_closed_path_c": diamond_box_p,
            "formula": "◇C ∧ □(C -> P)" if diamond_box_p else "◇P" if diamond_p else "UNPROVEN",
        },
        "closed_path_c": closed_path,
        "non_circularity_checks": non_circular,
        "evidence_items": evidence_items,
        "evidence_digests": evidence_digests,
        "construction_witness": {
            "schema_id": witness["schema_id"],
            "mode": witness["mode"],
            "profiles": witness["profiles"],
            "selected_tool_ids": witness["selected_tool_ids"],
            "pass_count": witness["pass_count"],
            "report_count": witness["report_count"],
            "fail_count": witness["fail_count"],
            "entry_labels": witness["entry_labels"],
            "judgment": witness["decision_report"]["judgment"],
            "tool_rows": [
                {
                    "tool_id": row["tool_id"],
                    "status": row["status"],
                    "reason_code": row["reason_code"],
                    "executed": row["executed"],
                    "evidence": row.get("evidence", {}),
                }
                for row in witness["tool_rows"]
            ],
        },
        "rejection_target": {
            "claim": "□¬P",
            "meaning": "haansaan completion is absolutely impossible in every allowed world",
            "rejected": diamond_p,
            "rejection_reason": "a finite, non-circular closed path C and an executed construction witness exist",
        },
        "srvl_boundary": {
            "current_full_completion_claim": False,
            "release_ready_claim": False,
            "truth_claim": False,
            "certificate_stage": "CONSTRUCTION_WITNESS_OBSERVED",
            "not_promoted_to_full_completion": True,
        },
        "next_actions_to_turn_certificate_into_completion": [
            "Persist replay/witness files for every core profile run.",
            "Add fixture and counterexample cases for every purpose profile.",
            "Add bounded performance gates for adapter count, runtime, memory, and output size.",
            "Bind optional external adapters through availability reports and version evidence.",
            "Run the certificate and all fixture suites in CI or an equivalent local release gate.",
        ],
        "completion_claim": False,
        "release_ready_claim": False,
        "truth_claim": False,
    }


def build_judgment(
    *,
    purpose: str,
    target_kinds: Iterable[str] = (),
    criteria_tags: Iterable[str] = (),
    mode: Mode = "check",
    allow_tools: Iterable[str] = (),
    profiles: Iterable[str] = (),
    artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if mode not in {"plan", "check", "run"}:
        raise ValueError("HAANSAAN_UNKNOWN_MODE")
    target_values = tuple(target_kinds)
    criteria_values = tuple(criteria_tags)
    allow_values = tuple(allow_tools)
    profile_values = tuple(profiles)
    expanded = _expand_profile_inputs(
        purpose=purpose,
        target_kinds=target_values,
        criteria_tags=criteria_values,
        profiles=profile_values,
    )
    purpose_tokens = _normalize_text(expanded["purpose"])
    target_tokens = _normalize_many(expanded["target_kinds"])
    criteria_tokens = _normalize_many(expanded["criteria_tags"])
    allow_set = {_normalize_tool_id(tool) for tool in allow_values}
    artifact_payload = dict(artifacts or {})
    entry_label_report = _build_entry_label_report(
        purpose=purpose,
        mode=mode,
        profiles=profile_values,
        target_kinds=target_values,
        criteria_tags=criteria_values,
        allow_tools=allow_values,
        artifacts=artifact_payload,
        expanded=expanded,
    )

    rows = []
    for adapter in TOOL_REGISTRY:
        match = _select_adapter(adapter, purpose_tokens, target_tokens, criteria_tokens, allow_set)
        if not match["selected"]:
            continue
        availability = (
            {"status": "NOT_CHECKED", "reason_code": "PLAN_ONLY", "path": ""}
            if mode == "plan"
            else _availability(adapter)
        )
        row = {
            "tool_id": adapter.tool_id,
            "display_name": adapter.display_name,
            "adapter_kind": adapter.adapter_kind,
            "selected": True,
            "selection_score": match["score"],
            "selection_reasons": match["reasons"],
            "availability": availability,
            "execute_requested": mode == "run",
            "executed": False,
            "status": _status_from_availability(mode, availability),
            "reason_code": availability["reason_code"],
            "decision_report": _adapter_decision_report(
                adapter=adapter,
                status=_status_from_availability(mode, availability),
                reason_code=availability["reason_code"],
                mode=mode,
                availability=availability,
                artifacts=artifact_payload,
                purpose=expanded["purpose"],
                entry_labels=entry_label_report["labels"],
                executed=False,
                evidence={},
            ),
        }
        if mode == "run":
            row.update(_run_selected_adapter(adapter, availability, artifact_payload, expanded["purpose"], entry_label_report["labels"]))
        rows.append(row)

    selected_count = len(rows)
    pass_count = sum(1 for row in rows if row["status"] == "PASS")
    report_count = sum(1 for row in rows if row["status"] == "REPORT")
    fail_count = sum(1 for row in rows if row["status"] == "FAIL")
    decision_report = _aggregate_decision_report(
        purpose=purpose,
        expanded=expanded,
        mode=mode,
        rows=rows,
        artifacts=artifact_payload,
        entry_labels=entry_label_report["labels"],
    )
    return {
        "schema_id": HAANSAAN_SCHEMA_ID,
        "ok": fail_count == 0,
        "mode": mode,
        "purpose": purpose,
        "expanded_purpose": expanded["purpose"],
        "profiles": list(profile_values),
        "profile_ids": expanded["profile_ids"],
        "entry_labels": entry_label_report["labels"],
        "entry_label_report": entry_label_report,
        "target_kinds": list(target_values),
        "expanded_target_kinds": expanded["target_kinds"],
        "criteria_tags": list(criteria_values),
        "expanded_criteria_tags": expanded["criteria_tags"],
        "selected_tool_count": selected_count,
        "selected_tool_ids": [row["tool_id"] for row in rows],
        "pass_count": pass_count,
        "report_count": report_count,
        "fail_count": fail_count,
        "all_registry_tool_count": len(TOOL_REGISTRY),
        "all_tools_triggered": selected_count == len(TOOL_REGISTRY),
        "tool_rows": rows,
        "decision_report": decision_report,
        "judgment_boundary": {
            "purpose_and_criteria_are_primary": True,
            "target_kind_is_secondary": True,
            "not_always_full_parallel_execution": True,
            "no_fake_data": True,
            "no_arbitrary_success_rate": True,
            "no_confidence_score_without_meta_evidence": True,
            "no_simulation_substitution": True,
            "profiles_select_entrypoints_not_full_execution": True,
            "builtin_gates_are_structural_not_truth_oracles": True,
            "missing_tool_yields_decision_report_not_hold_stop": True,
        },
        "completion_claim": False,
        "release_ready_claim": False,
        "truth_claim": False,
    }


def build_agent_call_response(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("HAANSAAN_AGENT_CALL_REQUEST_MUST_BE_OBJECT")
    purpose = str(request.get("purpose") or "").strip()
    if not purpose:
        raise ValueError("HAANSAAN_AGENT_CALL_PURPOSE_REQUIRED")
    mode = str(request.get("mode") or "check").strip()
    if mode not in {"plan", "check", "run"}:
        raise ValueError("HAANSAAN_AGENT_CALL_UNKNOWN_MODE")
    judgment = build_judgment(
        purpose=purpose,
        target_kinds=_request_string_list(request, "target_kinds"),
        criteria_tags=_request_string_list(request, "criteria_tags"),
        mode=mode,  # type: ignore[arg-type]
        allow_tools=_request_string_list(request, "allow_tools"),
        profiles=_request_string_list(request, "profiles"),
        artifacts=_request_dict(request, "artifacts"),
    )
    return {
        "schema_id": HAANSAAN_AGENT_CALL_RESPONSE_SCHEMA_ID,
        "ok": judgment["ok"],
        "request_schema_id": str(request.get("schema_id") or ""),
        "request_id": str(request.get("request_id") or ""),
        "caller": str(request.get("caller") or ""),
        "contract": {
            "callable_by_external_program": True,
            "stdin_json_supported": True,
            "file_json_supported": True,
            "stdout_json_only": True,
            "no_hidden_global_state": True,
            "no_network_required": True,
            "exit_0_when_no_probe_fail": True,
            "exit_1_when_probe_fail": True,
            "exit_2_when_invalid_request": True,
        },
        "judgment": judgment,
        "completion_claim": False,
        "release_ready_claim": False,
        "truth_claim": False,
    }


def build_agent_call_error_response(*, reason_code: str, error_summary: str) -> dict[str, Any]:
    return {
        "schema_id": HAANSAAN_AGENT_CALL_RESPONSE_SCHEMA_ID,
        "ok": False,
        "reason_code": reason_code,
        "error_summary": error_summary,
        "completion_claim": False,
        "release_ready_claim": False,
        "truth_claim": False,
    }


def _request_string_list(request: dict[str, Any], key: str) -> tuple[str, ...]:
    value = request.get(key, ())
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item).strip())
    raise ValueError(f"HAANSAAN_AGENT_CALL_{key.upper()}_MUST_BE_STRING_LIST")


def _request_dict(request: dict[str, Any], key: str) -> dict[str, Any]:
    value = request.get(key, {})
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    raise ValueError(f"HAANSAAN_AGENT_CALL_{key.upper()}_MUST_BE_OBJECT")


def _expand_profile_inputs(
    *,
    purpose: str,
    target_kinds: Iterable[str],
    criteria_tags: Iterable[str],
    profiles: Iterable[str],
) -> dict[str, Any]:
    profile_ids = tuple(_normalize_profile_id(profile) for profile in profiles if str(profile).strip())
    by_id = {profile.profile_id: profile for profile in PURPOSE_PROFILES}
    missing = [profile_id for profile_id in profile_ids if profile_id not in by_id]
    if missing:
        raise ValueError(f"HAANSAAN_UNKNOWN_PURPOSE_PROFILE:{','.join(missing)}")
    selected = [by_id[profile_id] for profile_id in profile_ids]
    purpose_parts = [purpose, *(term for profile in selected for term in profile.purpose_terms)]
    target_parts = [*target_kinds, *(target for profile in selected for target in profile.target_kinds)]
    criteria_parts = [*criteria_tags, *(criterion for profile in selected for criterion in profile.criteria_tags)]
    return {
        "purpose": " ".join(part for part in purpose_parts if str(part).strip()),
        "target_kinds": list(dict.fromkeys(str(item) for item in target_parts if str(item).strip())),
        "criteria_tags": list(dict.fromkeys(str(item) for item in criteria_parts if str(item).strip())),
        "profile_ids": list(profile_ids),
    }


def _normalize_profile_id(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _select_adapter(
    adapter: ToolAdapter,
    purpose_tokens: set[str],
    target_tokens: set[str],
    criteria_tokens: set[str],
    allow_set: set[str],
) -> dict[str, Any]:
    reasons: list[str] = []
    score = 0
    adapter_tool_id = _normalize_tool_id(adapter.tool_id)
    if adapter_tool_id in allow_set:
        reasons.append("allowlist")
        score += 4
    purpose_hits = purpose_tokens.intersection(adapter.purpose_axes)
    if purpose_hits:
        reasons.append("purpose_axis")
        score += 3 * len(purpose_hits)
    criteria_hits = criteria_tokens.intersection(adapter.criteria_tags)
    if criteria_hits:
        reasons.append("criteria_tag")
        score += 3 * len(criteria_hits)
    target_hits = target_tokens.intersection(adapter.target_kinds)
    if target_hits:
        reasons.append("target_kind")
        score += len(target_hits)
    selected = bool(adapter_tool_id in allow_set or purpose_hits or criteria_hits)
    return {"selected": selected, "score": score, "reasons": reasons}


def _availability(adapter: ToolAdapter) -> dict[str, str]:
    if adapter.adapter_kind == "builtin":
        return {"status": "AVAILABLE", "reason_code": "BUILTIN_ADAPTER", "path": "haansaan"}
    if adapter.import_name:
        found = importlib.util.find_spec(adapter.import_name)
        if found is None:
            return {"status": "UNAVAILABLE", "reason_code": "MISSING_PYTHON_MODULE", "path": ""}
        return {"status": "AVAILABLE", "reason_code": "PYTHON_MODULE_FOUND", "path": str(found.origin or "")}
    if adapter.command_name:
        path = shutil.which(adapter.command_name)
        if path is None:
            return {"status": "UNAVAILABLE", "reason_code": "MISSING_COMMAND", "path": ""}
        return {"status": "AVAILABLE", "reason_code": "COMMAND_FOUND", "path": path}
    return {"status": "UNAVAILABLE", "reason_code": "NO_ADAPTER_BINDING", "path": ""}


def _status_from_availability(_mode: Mode, _availability: dict[str, str]) -> RowStatus:
    return "REPORT"


def _run_selected_adapter(
    adapter: ToolAdapter,
    availability: dict[str, str],
    artifacts: dict[str, Any],
    purpose: str,
    entry_labels: list[str],
) -> dict[str, Any]:
    if availability["status"] != "AVAILABLE":
        reason_code = availability["reason_code"]
        return {
            "status": "REPORT",
            "reason_code": availability["reason_code"],
            "executed": False,
            "evidence": {},
            "decision_report": _adapter_decision_report(
                adapter=adapter,
                status="REPORT",
                reason_code=reason_code,
                mode="run",
                availability=availability,
                artifacts=artifacts,
                purpose=purpose,
                entry_labels=entry_labels,
                executed=False,
                evidence={},
            ),
        }
    if not adapter.safe_probe:
        reason_code = "NO_SAFE_NONINTERACTIVE_PROBE"
        return {
            "status": "REPORT",
            "reason_code": reason_code,
            "executed": False,
            "evidence": {},
            "decision_report": _adapter_decision_report(
                adapter=adapter,
                status="REPORT",
                reason_code=reason_code,
                mode="run",
                availability=availability,
                artifacts=artifacts,
                purpose=purpose,
                entry_labels=entry_labels,
                executed=False,
                evidence={},
            ),
        }
    probe = SAFE_PROBES.get(adapter.tool_id)
    builtin_probe = BUILTIN_PROBES.get(adapter.tool_id)
    if probe is None:
        if builtin_probe is not None:
            return _attach_entry_labels_to_result(builtin_probe(artifacts, purpose), entry_labels)
        reason_code = "PROBE_NOT_IMPLEMENTED"
        return {
            "status": "REPORT",
            "reason_code": reason_code,
            "executed": False,
            "evidence": {},
            "decision_report": _adapter_decision_report(
                adapter=adapter,
                status="REPORT",
                reason_code=reason_code,
                mode="run",
                availability=availability,
                artifacts=artifacts,
                purpose=purpose,
                entry_labels=entry_labels,
                executed=False,
                evidence={},
            ),
        }
    started_ns = time.perf_counter_ns()
    try:
        evidence = probe()
    except Exception as exc:
        return {
            "status": "FAIL",
            "reason_code": "PROBE_FAILED",
            "executed": True,
            "elapsed_ns": time.perf_counter_ns() - started_ns,
            "error_type": type(exc).__name__,
            "error_summary": str(exc)[:500],
            "evidence": {},
            "decision_report": _adapter_decision_report(
                adapter=adapter,
                status="FAIL",
                reason_code="PROBE_FAILED",
                mode="run",
                availability=availability,
                artifacts=artifacts,
                purpose=purpose,
                entry_labels=entry_labels,
                executed=True,
                evidence={"error_type": type(exc).__name__, "error_summary": str(exc)[:500]},
            ),
        }
    elapsed_ns = time.perf_counter_ns() - started_ns
    return {
        "status": "PASS",
        "reason_code": "EXECUTED_WITH_LOCAL_EVIDENCE",
        "executed": True,
        "elapsed_ns": elapsed_ns,
        "evidence": evidence,
        "decision_report": _adapter_decision_report(
            adapter=adapter,
            status="PASS",
            reason_code="EXECUTED_WITH_LOCAL_EVIDENCE",
            mode="run",
            availability=availability,
            artifacts=artifacts,
            purpose=purpose,
            entry_labels=entry_labels,
            executed=True,
            evidence=evidence,
            elapsed_ns=elapsed_ns,
        ),
    }


def _normalize_tool_id(value: str) -> str:
    return value.strip().lower().replace("-", "").replace("_", "")


def _normalize_text(value: str) -> set[str]:
    raw = {
        part.strip().lower()
        for part in value.replace(",", " ").replace("/", " ").replace(";", " ").split()
        if part.strip()
    }
    return {TOKEN_ALIASES.get(token, token) for token in raw}


def _normalize_many(values: Iterable[str]) -> set[str]:
    output: set[str] = set()
    for value in values:
        output.update(_normalize_text(value))
    return output


def _build_entry_label_report(
    *,
    purpose: str,
    mode: Mode,
    profiles: tuple[str, ...],
    target_kinds: tuple[str, ...],
    criteria_tags: tuple[str, ...],
    allow_tools: tuple[str, ...],
    artifacts: dict[str, Any],
    expanded: dict[str, Any],
) -> dict[str, Any]:
    labels: list[str] = [f"mode:{mode}"]
    if purpose.strip():
        labels.append("request:purpose")
    if profiles:
        labels.append("request:profile")
    if target_kinds:
        labels.append("request:target")
    if criteria_tags:
        labels.append("request:criteria")
    if allow_tools:
        labels.append("request:allow_tool")
    for profile_id in expanded["profile_ids"]:
        labels.append(f"profile:{profile_id}")
    for key in (
        "input_text",
        "output_text",
        "context_text",
        "claims",
        "evidence_refs",
        "memory_refs",
        "flow_steps",
        "artifact_paths",
        "resource_profile",
        "architecture_notes",
        "risk_items",
        "attack_scenarios",
        "review_scope",
        "maintenance_notes",
        "innovation_claims",
    ):
        if artifacts.get(key):
            labels.append(f"artifact:{key}")
    stable_labels = _unique_strings(labels)
    label_axis = _label_axis_map()
    return {
        "schema_id": "HAANSAAN_ENTRY_LABEL_REPORT_V1",
        "labels": stable_labels,
        "labels_by_axis": _labels_by_axis(stable_labels, label_axis),
        "unregistered_labels": [label for label in stable_labels if label not in label_axis],
        "routing_summary": {
            "profile_ids": expanded["profile_ids"],
            "artifact_keys": sorted(key for key, value in artifacts.items() if value),
            "mode": mode,
            "request_has_purpose": bool(purpose.strip()),
        },
        "trust_contract": {
            "same_input_same_labels": True,
            "labels_are_for_entry_routing": True,
            "labels_are_not_truth_claims": True,
            "labels_are_not_completion_claims": True,
        },
    }


def _label_axis_map() -> dict[str, str]:
    labels = {label.label_id: label.axis for label in ENTRY_LABEL_REGISTRY}
    labels.update({f"profile:{profile.profile_id}": "profile" for profile in PURPOSE_PROFILES})
    return labels


def _labels_by_axis(labels: Iterable[str], label_axis: dict[str, str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for label in labels:
        grouped.setdefault(label_axis.get(label, "unregistered"), []).append(label)
    return grouped


def _attach_entry_labels_to_result(result: dict[str, Any], entry_labels: list[str]) -> dict[str, Any]:
    report = result.get("decision_report")
    if isinstance(report, dict):
        understanding = report.setdefault("understanding", {})
        if isinstance(understanding, dict):
            understanding["entry_labels"] = entry_labels
    return result


def _adapter_decision_report(
    *,
    adapter: ToolAdapter,
    status: RowStatus,
    reason_code: str,
    mode: Mode,
    availability: dict[str, str],
    artifacts: dict[str, Any],
    purpose: str,
    entry_labels: list[str],
    executed: bool,
    evidence: dict[str, Any],
    elapsed_ns: int | None = None,
) -> dict[str, Any]:
    summary = _summary_for_reason(adapter, reason_code, status, mode)
    depth = _depth_measure(
        status=status,
        mode=mode,
        availability=availability,
        artifacts=artifacts,
        executed=executed,
        evidence=evidence,
    )
    return {
        "schema_id": "HAANSAAN_DECISION_REPORT_V1",
        "judgment": _judgment_for_status(status, reason_code),
        "understanding": {
            "purpose": purpose,
            "entry_labels": entry_labels,
            "adapter": adapter.tool_id,
            "adapter_kind": adapter.adapter_kind,
            "selected_for": {
                "purpose_axes": list(adapter.purpose_axes),
                "target_kinds": list(adapter.target_kinds),
                "criteria_tags": list(adapter.criteria_tags),
            },
        },
        "analysis": summary,
        "depth_measure": depth,
        "improvement_points": _improvement_points(reason_code, adapter, artifacts),
        "direction": _direction_for_reason(reason_code, adapter),
        "possible_worlds": _possible_worlds(reason_code, adapter),
        "next_actions": _next_actions_for_reason(reason_code, adapter, artifacts),
        "evidence_boundary": {
            "completion_claim": False,
            "truth_claim": False,
            "confidence_score_claim": False,
            "elapsed_ns": elapsed_ns,
        },
    }


def _builtin_decision_report(
    *,
    status: RowStatus,
    reason_code: str,
    summary: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_id": "HAANSAAN_DECISION_REPORT_V1",
        "judgment": _judgment_for_status(status, reason_code),
        "understanding": {
            "adapter": "builtin",
            "adapter_kind": "builtin",
            "evidence_keys": sorted(evidence.keys()),
        },
        "analysis": summary,
        "depth_measure": {
            "level": 4 if status == "PASS" else 2,
            "level_name": "structural_gate_evidence" if status == "PASS" else "actionable_structural_report",
            "not_confidence_score": True,
            "basis": ["builtin structural gate", *sorted(evidence.keys())],
        },
        "improvement_points": _generic_improvement_points(reason_code),
        "direction": _generic_direction(reason_code),
        "possible_worlds": _generic_possible_worlds(reason_code),
        "next_actions": _generic_next_actions(reason_code),
        "evidence_boundary": {
            "completion_claim": False,
            "truth_claim": False,
            "confidence_score_claim": False,
        },
    }


def _aggregate_decision_report(
    *,
    purpose: str,
    expanded: dict[str, Any],
    mode: Mode,
    rows: list[dict[str, Any]],
    artifacts: dict[str, Any],
    entry_labels: list[str],
) -> dict[str, Any]:
    report_rows = [row for row in rows if row["status"] == "REPORT"]
    fail_rows = [row for row in rows if row["status"] == "FAIL"]
    pass_rows = [row for row in rows if row["status"] == "PASS"]
    row_reports = [row.get("decision_report", {}) for row in rows]
    next_actions = _unique_strings(
        action
        for report in row_reports
        for action in report.get("next_actions", [])
    )
    improvement_points = _unique_strings(
        point
        for report in row_reports
        for point in report.get("improvement_points", [])
    )
    possible_worlds = _unique_dicts(
        world
        for report in row_reports
        for world in report.get("possible_worlds", [])
        if isinstance(world, dict)
    )
    deepest_level = max(
        (int(report.get("depth_measure", {}).get("level") or 0) for report in row_reports),
        default=0,
    )
    return {
        "schema_id": "HAANSAAN_AGGREGATE_DECISION_REPORT_V1",
        "judgment": _aggregate_judgment(pass_rows=pass_rows, report_rows=report_rows, fail_rows=fail_rows),
        "understanding": {
            "purpose": purpose,
            "expanded_purpose": expanded["purpose"],
            "profile_ids": expanded["profile_ids"],
            "entry_labels": entry_labels,
            "mode": mode,
            "artifact_keys": sorted(artifacts.keys()),
            "selected_tool_ids": [row["tool_id"] for row in rows],
        },
        "analysis": _aggregate_analysis(pass_rows=pass_rows, report_rows=report_rows, fail_rows=fail_rows),
        "depth_measure": {
            "deepest_level": deepest_level,
            "selected_tool_count": len(rows),
            "pass_count": len(pass_rows),
            "report_count": len(report_rows),
            "fail_count": len(fail_rows),
            "not_confidence_score": True,
        },
        "improvement_points": improvement_points,
        "direction": _aggregate_direction(pass_rows=pass_rows, report_rows=report_rows, fail_rows=fail_rows),
        "possible_worlds": possible_worlds,
        "next_actions": next_actions,
        "evidence_boundary": {
            "completion_claim": False,
            "truth_claim": False,
            "confidence_score_claim": False,
            "report_is_for_next_action_decision": True,
        },
    }


def _depth_measure(
    *,
    status: RowStatus,
    mode: Mode,
    availability: dict[str, str],
    artifacts: dict[str, Any],
    executed: bool,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    artifact_signal_count = sum(1 for value in artifacts.values() if bool(value))
    evidence_key_count = len(evidence)
    if status == "FAIL":
        level = 5 if executed else 2
        level_name = "executed_failure_evidence" if executed else "blocking_input_failure"
    elif status == "PASS" and executed:
        level = 4
        level_name = "local_probe_evidence"
    elif availability["status"] == "AVAILABLE":
        level = 2
        level_name = "availability_and_selection_report"
    elif mode == "plan":
        level = 1
        level_name = "entrypoint_selection_report"
    else:
        level = 2
        level_name = "missing_capability_decision_report"
    return {
        "level": level,
        "level_name": level_name,
        "mode": mode,
        "availability_status": availability["status"],
        "executed": executed,
        "artifact_signal_count": artifact_signal_count,
        "evidence_key_count": evidence_key_count,
        "not_confidence_score": True,
    }


def _summary_for_reason(adapter: ToolAdapter, reason_code: str, status: RowStatus, mode: Mode) -> str:
    if status == "PASS":
        return f"{adapter.tool_id} produced bounded local evidence for the selected purpose."
    if status == "FAIL":
        return f"{adapter.tool_id} executed and failed; inspect error evidence before using this branch."
    if mode == "plan":
        return f"{adapter.tool_id} is selected as a relevant entrypoint; execution was not requested."
    if reason_code == "MISSING_PYTHON_MODULE":
        return f"{adapter.tool_id} is relevant, but its Python module is not installed in this environment."
    if reason_code == "MISSING_COMMAND":
        return f"{adapter.tool_id} is relevant, but its command is not on PATH."
    if reason_code == "NO_SAFE_NONINTERACTIVE_PROBE":
        return f"{adapter.tool_id} is relevant and may be available, but no bounded safe probe is defined."
    if reason_code == "PROBE_NOT_IMPLEMENTED":
        return f"{adapter.tool_id} is relevant, but haansaan has no executable probe binding yet."
    return f"{adapter.tool_id} produced an actionable decision report for reason {reason_code}."


def _judgment_for_status(status: RowStatus, reason_code: str) -> str:
    if status == "PASS":
        return "EVIDENCE_AVAILABLE"
    if status == "FAIL":
        return "FAILED_EVIDENCE_REQUIRES_REPAIR"
    if reason_code in {"MISSING_PYTHON_MODULE", "MISSING_COMMAND", "NO_ADAPTER_BINDING"}:
        return "CAPABILITY_GAP_MEASURED_NEXT_ACTION_REQUIRED"
    if reason_code.startswith("QUALITY_") or reason_code.endswith("_REQUIRED"):
        return "INPUT_GAP_MEASURED_NEXT_ACTION_REQUIRED"
    return "REPORT_AVAILABLE_NEXT_ACTION_REQUIRED"


def _improvement_points(reason_code: str, adapter: ToolAdapter, artifacts: dict[str, Any]) -> list[str]:
    points = _generic_improvement_points(reason_code)
    if adapter.adapter_kind in {"python_module", "command"}:
        points.append(f"Bind {adapter.tool_id} installation and version into the local capability registry.")
    if not artifacts:
        points.append("Pass bounded artifacts so the report can inspect real input/output/workflow evidence.")
    return _unique_strings(points)


def _direction_for_reason(reason_code: str, adapter: ToolAdapter) -> str:
    if reason_code == "MISSING_PYTHON_MODULE":
        return f"Install the Python package for {adapter.tool_id}, or route this purpose to a built-in structural report until that dependency is available."
    if reason_code == "MISSING_COMMAND":
        return f"Install or expose the {adapter.command_name or adapter.tool_id} command on PATH, then rerun the same profile."
    if reason_code == "NO_SAFE_NONINTERACTIVE_PROBE":
        return f"Keep {adapter.tool_id} as a selectable adapter, but add a bounded noninteractive probe before run-mode evidence is trusted."
    return _generic_direction(reason_code)


def _possible_worlds(reason_code: str, adapter: ToolAdapter) -> list[dict[str, Any]]:
    worlds = _generic_possible_worlds(reason_code)
    if reason_code in {"MISSING_PYTHON_MODULE", "MISSING_COMMAND"}:
        worlds.append(
            {
                "world_id": "capability_installed",
                "condition": f"{adapter.tool_id} becomes available locally",
                "expected_effect": "same request can advance from REPORT to executable local evidence",
            }
        )
    if reason_code == "NO_SAFE_NONINTERACTIVE_PROBE":
        worlds.append(
            {
                "world_id": "safe_probe_added",
                "condition": f"haansaan defines a bounded safe probe for {adapter.tool_id}",
                "expected_effect": "run mode can execute without manual or unbounded behavior",
            }
        )
    return worlds


def _next_actions_for_reason(reason_code: str, adapter: ToolAdapter, artifacts: dict[str, Any]) -> list[str]:
    actions = _generic_next_actions(reason_code)
    if reason_code == "MISSING_PYTHON_MODULE" and adapter.import_name:
        actions.append(f"Install Python module `{adapter.import_name}` in the haansaan runtime.")
    if reason_code == "MISSING_COMMAND" and adapter.command_name:
        actions.append(f"Install `{adapter.command_name}` or add it to PATH.")
    if reason_code == "NO_SAFE_NONINTERACTIVE_PROBE":
        actions.append(f"Add a bounded probe for `{adapter.tool_id}` before expecting run-mode evidence.")
    if not artifacts:
        actions.append("Send artifacts in the JSON request: input_text, output_text, context_text, evidence_refs, flow_steps, memory_refs, or artifact_paths as applicable.")
    return _unique_strings(actions)


def _generic_improvement_points(reason_code: str) -> list[str]:
    if reason_code == "BUILTIN_STRUCTURAL_CHECK_PASS":
        return ["Structural gate passed for the supplied labels; deepen with target-specific external adapters if the decision requires stronger evidence."]
    if reason_code == "EXECUTED_WITH_LOCAL_EVIDENCE":
        return ["Move from environment probe evidence to target-specific artifact evidence before claiming task completion."]
    mapping = {
        "ARTIFACT_IO_INPUT_REQUIRED": ["Supply at least one input/output text field or artifact path."],
        "SEMANTIC_LOGIC_CLAIMS_REQUIRED": ["Supply explicit claims before semantic logic review."],
        "SEMANTIC_LOGIC_EVIDENCE_REQUIRED": ["Attach evidence_refs for each claim family."],
        "PURPOSE_DRIFT_OUTPUT_REQUIRED": ["Supply output_text so purpose preservation can be inspected."],
        "PURPOSE_TRACE_WEAK": ["Make the output carry explicit purpose/direction trace, or pass richer purpose terms."],
        "CONTEXT_TRACE_FLOW_STEPS_REQUIRED": ["Supply flow_steps to reconstruct sequence and replay boundary."],
        "MEMORY_REFS_REQUIRED": ["Supply memory_refs with source boundaries."],
        "CONTAMINATION_TEXT_REQUIRED": ["Supply input_text, output_text, or context_text for contamination scanning."],
        "STABILITY_EVIDENCE_REQUIRED": ["Supply resource_profile or flow_steps for stability review."],
        "QUALITY_OUTPUT_REQUIRED": ["Supply output_text for quality review."],
        "QUALITY_EVIDENCE_REFS_REQUIRED": ["Supply evidence_refs so quality judgment is not surface-only."],
        "CODE_REVIEW_INPUT_REQUIRED": ["Supply code text, artifact_paths, or review_scope."],
        "CODE_REVIEW_SURFACE_REPORT": ["Add concrete changed files, linter output, or review scope to deepen code review."],
        "CODE_SECURITY_INPUT_REQUIRED": ["Supply code text, artifact_paths, or risk_items."],
        "CODE_SECURITY_SURFACE_REPORT": ["Run external SAST/dependency tools when security confidence is required."],
        "CODE_SECURITY_RISK_MARKERS_REPORT": ["Inspect reported risk markers manually and run security-specific tools."],
        "ATTACK_VERIFICATION_INPUT_REQUIRED": ["Supply attack_scenarios, risk_items, flow_steps, or context text."],
        "ATTACK_VERIFICATION_SURFACE_REPORT": ["Turn reported attack surfaces into concrete test cases or threat-model checks."],
        "ARCHITECTURE_INPUT_REQUIRED": ["Supply architecture_notes, flow_steps, artifact_paths, or context text."],
        "ARCHITECTURE_MEASUREMENT_REPORT": ["Add module/interface/data-flow evidence to strengthen architecture measurement."],
        "COMPLEXITY_INPUT_REQUIRED": ["Supply text, artifact_paths, or flow_steps."],
        "COMPLEXITY_LEVEL_REPORT": ["Compare measured level with resource, testing, and maintainability budgets."],
        "MAINTAINABILITY_INPUT_REQUIRED": ["Supply maintenance notes, artifact paths, or evidence refs."],
        "MAINTAINABILITY_MEASUREMENT_REPORT": ["Add ownership, docs, dependency, and test evidence for stronger maintainability judgment."],
        "INNOVATION_INPUT_REQUIRED": ["Supply innovation_claims, claims, or descriptive text."],
        "INNOVATION_MEASUREMENT_REPORT": ["Add baseline comparison and evidence_refs before making strong innovation claims."],
    }
    return list(mapping.get(reason_code, ["Use this report to choose install, reroute, artifact enrichment, or bounded probe implementation."]))


def _generic_direction(reason_code: str) -> str:
    if reason_code == "BUILTIN_STRUCTURAL_CHECK_PASS":
        return "Treat this as structural evidence for the labeled entry, not as a truth or completion proof."
    if reason_code == "EXECUTED_WITH_LOCAL_EVIDENCE":
        return "Use the successful local probe as capability evidence, then run against the actual target artifact if completion is being considered."
    if reason_code.endswith("_REQUIRED"):
        return "Enrich the request artifact packet, then rerun the same profile."
    if reason_code == "PURPOSE_TRACE_WEAK":
        return "Inspect whether the output lost the original purpose, then repair the output or provide stronger purpose anchors."
    if reason_code in {"MISSING_PYTHON_MODULE", "MISSING_COMMAND"}:
        return "Resolve the capability gap or accept a structural report for this iteration."
    return "Use the measured gap to choose the next bounded action."


def _generic_possible_worlds(reason_code: str) -> list[dict[str, Any]]:
    if reason_code == "BUILTIN_STRUCTURAL_CHECK_PASS":
        return [
            {
                "world_id": "structural_gate_sufficient",
                "condition": "current decision only needs bounded structural routing evidence",
                "expected_effect": "caller may proceed to the next workflow step without claiming final truth",
            },
            {
                "world_id": "deeper_external_evidence_required",
                "condition": "caller needs mathematical, code, formal, NLP, or security-grade proof",
                "expected_effect": "rerun with the matching profile and target artifacts",
            },
        ]
    if reason_code == "EXECUTED_WITH_LOCAL_EVIDENCE":
        return [
            {
                "world_id": "target_artifact_supplied",
                "condition": "caller supplies real target artifacts and evidence references",
                "expected_effect": "haansaan can move from capability evidence to task-specific review evidence",
            },
            {
                "world_id": "probe_only",
                "condition": "caller does not supply real target artifacts",
                "expected_effect": "evidence remains environment capability proof only, not task completion proof",
            },
        ]
    if reason_code.endswith("_REQUIRED"):
        return [
            {
                "world_id": "artifact_enriched",
                "condition": "caller supplies the missing artifact field",
                "expected_effect": "same selected gate can move from REPORT to stronger structural evidence",
            },
            {
                "world_id": "artifact_unavailable",
                "condition": "caller cannot supply the missing artifact field",
                "expected_effect": "decision should remain report-only and avoid false completion",
            },
        ]
    return [
        {
            "world_id": "bounded_next_action",
            "condition": "caller follows the report next_actions",
            "expected_effect": "next run has stronger evidence or a clearer blocker",
        }
    ]


def _generic_next_actions(reason_code: str) -> list[str]:
    if reason_code == "BUILTIN_STRUCTURAL_CHECK_PASS":
        return ["Proceed only within the labeled scope, or rerun with a deeper profile and target artifacts if stronger evidence is needed."]
    if reason_code == "EXECUTED_WITH_LOCAL_EVIDENCE":
        return ["Rerun with target artifacts when judging a real task: artifact_paths, input_text, output_text, claims, evidence_refs, flow_steps, memory_refs, or resource_profile as applicable."]
    mapping = {
        "ARTIFACT_IO_INPUT_REQUIRED": ["Add `input_text`, `output_text`, or `artifact_paths` to artifacts."],
        "SEMANTIC_LOGIC_CLAIMS_REQUIRED": ["Add `claims` to artifacts."],
        "SEMANTIC_LOGIC_EVIDENCE_REQUIRED": ["Add `evidence_refs` to artifacts."],
        "PURPOSE_DRIFT_OUTPUT_REQUIRED": ["Add `output_text` to artifacts."],
        "PURPOSE_TRACE_WEAK": ["Repair output_text to expose purpose/direction trace or pass more explicit purpose terms."],
        "CONTEXT_TRACE_FLOW_STEPS_REQUIRED": ["Add `flow_steps` to artifacts."],
        "MEMORY_REFS_REQUIRED": ["Add `memory_refs` to artifacts."],
        "CONTAMINATION_TEXT_REQUIRED": ["Add `input_text`, `output_text`, or `context_text` to artifacts."],
        "STABILITY_EVIDENCE_REQUIRED": ["Add `resource_profile` or `flow_steps` to artifacts."],
        "QUALITY_OUTPUT_REQUIRED": ["Add `output_text` to artifacts."],
        "QUALITY_EVIDENCE_REFS_REQUIRED": ["Add `evidence_refs` to artifacts."],
        "CODE_REVIEW_INPUT_REQUIRED": ["Add `output_text`, `artifact_paths`, or `review_scope` to artifacts."],
        "CODE_REVIEW_SURFACE_REPORT": ["Run `code_review` again with concrete files and linter/test evidence."],
        "CODE_SECURITY_INPUT_REQUIRED": ["Add `output_text`, `artifact_paths`, or `risk_items` to artifacts."],
        "CODE_SECURITY_SURFACE_REPORT": ["Run `code_security` with Semgrep/Bandit/pip-audit when available, or add concrete risk_items."],
        "CODE_SECURITY_RISK_MARKERS_REPORT": ["Treat simple risk markers as review targets, not proof; run external security tools or manual audit."],
        "ATTACK_VERIFICATION_INPUT_REQUIRED": ["Add `attack_scenarios`, `risk_items`, `flow_steps`, or `context_text` to artifacts."],
        "ATTACK_VERIFICATION_SURFACE_REPORT": ["Convert reported attack surface into concrete adversarial tests or threat-model evidence."],
        "ARCHITECTURE_INPUT_REQUIRED": ["Add `architecture_notes`, `flow_steps`, `artifact_paths`, or `context_text` to artifacts."],
        "ARCHITECTURE_MEASUREMENT_REPORT": ["Use architecture measurement to decide refactor, boundary clarification, or deeper review."],
        "COMPLEXITY_INPUT_REQUIRED": ["Add `architecture_notes`, `artifact_paths`, `flow_steps`, or text artifacts."],
        "COMPLEXITY_LEVEL_REPORT": ["Use complexity level to decide whether to split scope, add tests, or reduce coupling."],
        "MAINTAINABILITY_INPUT_REQUIRED": ["Add `maintenance_notes`, `artifact_paths`, or `evidence_refs` to artifacts."],
        "MAINTAINABILITY_MEASUREMENT_REPORT": ["Use maintainability report to choose documentation, ownership, dependency, or test work."],
        "INNOVATION_INPUT_REQUIRED": ["Add `innovation_claims`, `claims`, or descriptive text to artifacts."],
        "INNOVATION_MEASUREMENT_REPORT": ["Add baseline comparison and evidence_refs before presenting an innovation claim."],
    }
    return list(mapping.get(reason_code, ["Choose one next action: install capability, provide artifact evidence, implement bounded probe, or reroute to a structural builtin gate."]))


def _aggregate_judgment(*, pass_rows: list[dict[str, Any]], report_rows: list[dict[str, Any]], fail_rows: list[dict[str, Any]]) -> str:
    if fail_rows:
        return "FAIL_REPAIR_REQUIRED"
    if report_rows and pass_rows:
        return "MIXED_EVIDENCE_AND_REPORT_NEXT_ACTION_REQUIRED"
    if report_rows:
        return "REPORT_ONLY_NEXT_ACTION_REQUIRED"
    if pass_rows:
        return "BOUNDED_EVIDENCE_AVAILABLE"
    return "NO_RELEVANT_ENTRYPOINT_SELECTED"


def _aggregate_analysis(*, pass_rows: list[dict[str, Any]], report_rows: list[dict[str, Any]], fail_rows: list[dict[str, Any]]) -> str:
    if fail_rows:
        return "At least one selected adapter failed during execution; repair the failed path before trusting the workflow."
    if report_rows and pass_rows:
        return "Some selected adapters produced bounded evidence while others produced decision reports; choose next actions from the measured gaps."
    if report_rows:
        return "The request did not stop at absence or missing input; haansaan produced decision reports for next action selection."
    if pass_rows:
        return "All selected adapters produced bounded local evidence; this is still not a completion or truth claim."
    return "No adapter was selected; refine purpose/profile/criteria."


def _aggregate_direction(*, pass_rows: list[dict[str, Any]], report_rows: list[dict[str, Any]], fail_rows: list[dict[str, Any]]) -> str:
    if fail_rows:
        return "Repair failed probes first, then rerun the same purpose profile."
    if report_rows:
        return "Use next_actions to enrich artifacts, install optional capabilities, or add bounded probes; then rerun without expanding scope."
    if pass_rows:
        return "If this was only a probe, move to target-specific artifact evidence before claiming completion."
    return "Narrow or clarify purpose so at least one profile or adapter is selected."


def _unique_strings(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _unique_dicts(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _artifact_text(artifacts: dict[str, Any], key: str) -> str:
    return str(artifacts.get(key) or "").strip()


def _artifact_list(artifacts: dict[str, Any], key: str) -> list[Any]:
    value = artifacts.get(key, [])
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value:
        return [value]
    return []


def _builtin_pass(summary: str, evidence: dict[str, Any]) -> dict[str, Any]:
    payload = {"summary": summary, **evidence}
    return {
        "status": "PASS",
        "reason_code": "BUILTIN_STRUCTURAL_CHECK_PASS",
        "executed": True,
        "evidence": payload,
        "decision_report": _builtin_decision_report(
            status="PASS",
            reason_code="BUILTIN_STRUCTURAL_CHECK_PASS",
            summary=summary,
            evidence=payload,
        ),
    }


def _builtin_report(reason_code: str, summary: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"summary": summary, **(evidence or {})}
    return {
        "status": "REPORT",
        "reason_code": reason_code,
        "executed": True,
        "evidence": payload,
        "decision_report": _builtin_decision_report(
            status="REPORT",
            reason_code=reason_code,
            summary=summary,
            evidence=payload,
        ),
    }


def _builtin_fail(reason_code: str, summary: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"summary": summary, **(evidence or {})}
    return {
        "status": "FAIL",
        "reason_code": reason_code,
        "executed": True,
        "evidence": payload,
        "decision_report": _builtin_decision_report(
            status="FAIL",
            reason_code=reason_code,
            summary=summary,
            evidence=payload,
        ),
    }


def _probe_artifact_io_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    input_text = _artifact_text(artifacts, "input_text")
    output_text = _artifact_text(artifacts, "output_text")
    paths = _artifact_list(artifacts, "artifact_paths")
    size_bytes = len(input_text.encode()) + len(output_text.encode())
    if not input_text and not output_text and not paths:
        return _builtin_report("ARTIFACT_IO_INPUT_REQUIRED", "no input/output/artifact path supplied")
    missing_paths = [
        str(path)
        for path in paths
        if str(path).strip().startswith(("/", "."))
        and not Path(str(path)).expanduser().exists()
    ]
    if missing_paths:
        return _builtin_fail("ARTIFACT_PATH_MISSING", "one or more local artifact paths are missing", {"missing_paths": missing_paths[:20]})
    return _builtin_pass(
        "artifact I/O boundary observed",
        {
            "input_present": bool(input_text),
            "output_present": bool(output_text),
            "artifact_path_count": len(paths),
            "local_artifact_path_count": sum(1 for path in paths if str(path).strip().startswith(("/", "."))),
            "observed_text_bytes": size_bytes,
        },
    )


def _probe_semantic_logic_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    claims = _artifact_list(artifacts, "claims")
    evidence_refs = _artifact_list(artifacts, "evidence_refs")
    if not claims:
        return _builtin_report("SEMANTIC_LOGIC_CLAIMS_REQUIRED", "no claims supplied for semantic logic review")
    if not evidence_refs:
        return _builtin_report("SEMANTIC_LOGIC_EVIDENCE_REQUIRED", "claims supplied without evidence references", {"claim_count": len(claims)})
    return _builtin_pass("claims have explicit evidence references", {"claim_count": len(claims), "evidence_ref_count": len(evidence_refs)})


def _probe_purpose_drift_builtin(artifacts: dict[str, Any], purpose: str) -> dict[str, Any]:
    output_text = _artifact_text(artifacts, "output_text")
    if not output_text:
        return _builtin_report("PURPOSE_DRIFT_OUTPUT_REQUIRED", "output_text required for purpose drift review")
    purpose_tokens = {token for token in _normalize_text(purpose) if len(token) >= 3}
    output_tokens = _normalize_text(output_text)
    overlap = sorted(purpose_tokens.intersection(output_tokens))
    if not overlap:
        return _builtin_report("PURPOSE_TRACE_WEAK", "no direct purpose-token overlap in output_text", {"purpose_token_count": len(purpose_tokens)})
    return _builtin_pass("purpose tokens are traceable in output_text", {"overlap": overlap[:20]})


def _probe_context_trace_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    flow_steps = _artifact_list(artifacts, "flow_steps")
    if not flow_steps:
        return _builtin_report("CONTEXT_TRACE_FLOW_STEPS_REQUIRED", "flow_steps required for context/flow review")
    return _builtin_pass("flow steps supplied for trace review", {"flow_step_count": len(flow_steps)})


def _probe_memory_boundary_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    memory_refs = _artifact_list(artifacts, "memory_refs")
    if not memory_refs:
        return _builtin_report("MEMORY_REFS_REQUIRED", "memory_refs required for memory boundary review")
    return _builtin_pass("memory references supplied", {"memory_ref_count": len(memory_refs)})


def _probe_contamination_guard_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    joined = "\n".join(
        str(artifacts.get(key) or "")
        for key in ("input_text", "output_text", "context_text")
    )
    if not joined.strip():
        return _builtin_report("CONTAMINATION_TEXT_REQUIRED", "input/output/context text required for contamination scan")
    lowered = joined.lower()
    suspicious = [marker for marker in ("api_key", "secret", "password", "private key", "token=") if marker in lowered]
    if suspicious:
        return _builtin_fail("POSSIBLE_SECRET_OR_PRIVATE_MARKER", "possible private marker found", {"markers": suspicious})
    return _builtin_pass("no simple private markers found", {"scanned_chars": len(joined)})


def _probe_stability_guard_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    resource_profile = artifacts.get("resource_profile")
    flow_steps = _artifact_list(artifacts, "flow_steps")
    if not resource_profile and not flow_steps:
        return _builtin_report("STABILITY_EVIDENCE_REQUIRED", "resource_profile or flow_steps required for stability review")
    return _builtin_pass("stability evidence supplied", {"has_resource_profile": isinstance(resource_profile, dict), "flow_step_count": len(flow_steps)})


def _probe_quality_management_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    output_text = _artifact_text(artifacts, "output_text")
    evidence_refs = _artifact_list(artifacts, "evidence_refs")
    next_actions = _artifact_list(artifacts, "next_actions")
    if not output_text:
        return _builtin_report("QUALITY_OUTPUT_REQUIRED", "output_text required for quality/management review")
    if not evidence_refs:
        return _builtin_report("QUALITY_EVIDENCE_REFS_REQUIRED", "evidence_refs required for quality/management review")
    return _builtin_pass("quality/management evidence supplied", {"output_chars": len(output_text), "evidence_ref_count": len(evidence_refs), "next_action_count": len(next_actions)})


def _artifact_joined_text(artifacts: dict[str, Any], keys: tuple[str, ...] = ("input_text", "output_text", "context_text")) -> str:
    return "\n".join(str(artifacts.get(key) or "") for key in keys).strip()


def _probe_code_review_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    text = _artifact_joined_text(artifacts)
    paths = _artifact_list(artifacts, "artifact_paths")
    review_scope = _artifact_text(artifacts, "review_scope")
    if not text and not paths and not review_scope:
        return _builtin_report("CODE_REVIEW_INPUT_REQUIRED", "code text, artifact_paths, or review_scope required for code review")
    signals = {
        "has_code_text": bool(text),
        "artifact_path_count": len(paths),
        "has_review_scope": bool(review_scope),
        "line_count": len(text.splitlines()) if text else 0,
    }
    return _builtin_report("CODE_REVIEW_SURFACE_REPORT", "code review surface measured", signals)


def _probe_code_safety_security_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    text = _artifact_joined_text(artifacts)
    paths = _artifact_list(artifacts, "artifact_paths")
    risk_items = _artifact_list(artifacts, "risk_items")
    if not text and not paths and not risk_items:
        return _builtin_report("CODE_SECURITY_INPUT_REQUIRED", "code text, artifact_paths, or risk_items required for code security review")
    lowered = text.lower()
    markers = [
        marker
        for marker in ("eval(", "exec(", "shell=true", "pickle.loads", "yaml.load(", "subprocess", "os.system", "token=", "password", "private key")
        if marker in lowered
    ]
    reason = "CODE_SECURITY_RISK_MARKERS_REPORT" if markers else "CODE_SECURITY_SURFACE_REPORT"
    return _builtin_report(
        reason,
        "code security risk surface measured",
        {
            "artifact_path_count": len(paths),
            "risk_item_count": len(risk_items),
            "simple_risk_markers": markers[:20],
            "simple_risk_marker_count": len(markers),
        },
    )


def _probe_adversarial_attack_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    attack_scenarios = _artifact_list(artifacts, "attack_scenarios")
    risk_items = _artifact_list(artifacts, "risk_items")
    flow_steps = _artifact_list(artifacts, "flow_steps")
    text = _artifact_joined_text(artifacts)
    if not attack_scenarios and not risk_items and not flow_steps and not text:
        return _builtin_report("ATTACK_VERIFICATION_INPUT_REQUIRED", "attack_scenarios, risk_items, flow_steps, or context text required")
    return _builtin_report(
        "ATTACK_VERIFICATION_SURFACE_REPORT",
        "attack verification surface measured",
        {
            "attack_scenario_count": len(attack_scenarios),
            "risk_item_count": len(risk_items),
            "flow_step_count": len(flow_steps),
            "has_context_text": bool(text),
            "requires_manual_or_external_attack_execution": True,
        },
    )


def _probe_system_architecture_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    architecture_notes = _artifact_text(artifacts, "architecture_notes")
    flow_steps = _artifact_list(artifacts, "flow_steps")
    paths = _artifact_list(artifacts, "artifact_paths")
    text = architecture_notes or _artifact_joined_text(artifacts)
    if not text and not flow_steps and not paths:
        return _builtin_report("ARCHITECTURE_INPUT_REQUIRED", "architecture_notes, flow_steps, artifact_paths, or context text required")
    lowered = text.lower()
    signals = {
        "module_boundary_mentions": _count_markers(lowered, ("module", "boundary", "interface", "adapter", "profile", "label")),
        "data_flow_mentions": _count_markers(lowered, ("flow", "pipeline", "input", "output", "state", "trace")),
        "operational_mentions": _count_markers(lowered, ("rollback", "resource", "runtime", "reentry", "version", "test")),
        "flow_step_count": len(flow_steps),
        "artifact_path_count": len(paths),
    }
    signals["structure_level"] = _bounded_level(sum(signals.values()))
    return _builtin_report("ARCHITECTURE_MEASUREMENT_REPORT", "system architecture quality surface measured", signals)


def _probe_complexity_level_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    text = _artifact_joined_text(artifacts, ("input_text", "output_text", "context_text", "architecture_notes"))
    paths = _artifact_list(artifacts, "artifact_paths")
    flow_steps = _artifact_list(artifacts, "flow_steps")
    if not text and not paths and not flow_steps:
        return _builtin_report("COMPLEXITY_INPUT_REQUIRED", "text, artifact_paths, or flow_steps required for complexity measurement")
    signal_total = len(paths) + len(flow_steps) + _count_markers(text.lower(), ("module", "adapter", "state", "dependency", "async", "queue", "security", "rollback"))
    return _builtin_report(
        "COMPLEXITY_LEVEL_REPORT",
        "complexity and difficulty surface measured",
        {
            "complexity_level": _bounded_level(signal_total),
            "artifact_path_count": len(paths),
            "flow_step_count": len(flow_steps),
            "text_chars": len(text),
        },
    )


def _probe_maintainability_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    text = _artifact_joined_text(artifacts, ("input_text", "output_text", "context_text", "maintenance_notes", "architecture_notes"))
    paths = _artifact_list(artifacts, "artifact_paths")
    evidence_refs = _artifact_list(artifacts, "evidence_refs")
    if not text and not paths and not evidence_refs:
        return _builtin_report("MAINTAINABILITY_INPUT_REQUIRED", "maintenance notes, artifact paths, or evidence refs required")
    lowered = text.lower()
    signals = {
        "ownership_mentions": _count_markers(lowered, ("owner", "ownership", "responsibility", "manager")),
        "documentation_mentions": _count_markers(lowered, ("readme", "doc", "document", "spec", "contract")),
        "dependency_mentions": _count_markers(lowered, ("dependency", "version", "lock", "package")),
        "test_mentions": _count_markers(lowered, ("test", "pytest", "verify", "lint")),
        "artifact_path_count": len(paths),
        "evidence_ref_count": len(evidence_refs),
    }
    signals["maintainability_level"] = _bounded_level(sum(signals.values()))
    return _builtin_report("MAINTAINABILITY_MEASUREMENT_REPORT", "maintainability surface measured", signals)


def _probe_innovation_builtin(artifacts: dict[str, Any], _purpose: str) -> dict[str, Any]:
    claims = _artifact_list(artifacts, "innovation_claims") or _artifact_list(artifacts, "claims")
    evidence_refs = _artifact_list(artifacts, "evidence_refs")
    text = _artifact_joined_text(artifacts)
    if not claims and not text:
        return _builtin_report("INNOVATION_INPUT_REQUIRED", "innovation_claims, claims, or descriptive text required")
    lowered = text.lower()
    signals = {
        "innovation_claim_count": len(claims),
        "evidence_ref_count": len(evidence_refs),
        "novelty_mentions": _count_markers(lowered, ("novel", "new", "innovation", "different", "differentiation", "unique")),
        "practicality_mentions": _count_markers(lowered, ("use", "workflow", "runtime", "test", "deploy", "maintain")),
        "comparison_mentions": _count_markers(lowered, ("compared", "alternative", "baseline", "existing")),
    }
    signals["innovation_evidence_level"] = _bounded_level(sum(signals.values()))
    return _builtin_report("INNOVATION_MEASUREMENT_REPORT", "innovation and novelty surface measured", signals)


def _count_markers(text: str, markers: tuple[str, ...]) -> int:
    return sum(1 for marker in markers if marker in text)


def _bounded_level(value: int) -> int:
    if value <= 0:
        return 0
    if value <= 2:
        return 1
    if value <= 5:
        return 2
    if value <= 9:
        return 3
    if value <= 14:
        return 4
    return 5


def _run_subprocess(command: list[str], *, input_text: str | None = None, timeout_s: int = 8) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout_s,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _probe_z3() -> dict[str, Any]:
    import z3  # type: ignore[import-not-found]

    x = z3.Int("x")
    solver = z3.Solver()
    solver.add(x == 6)
    result = str(solver.check())
    return {"summary": f"z3 probe returned {result}", "result": result}


def _probe_cvc5() -> dict[str, Any]:
    smt = "(set-logic QF_LIA)\n(declare-const x Int)\n(assert (= x 6))\n(check-sat)\n(get-value (x))\n"
    completed = _run_subprocess(["cvc5", "--lang", "smt2", "--produce-models"], input_text=smt)
    if "sat" not in completed["stdout"]:
        raise RuntimeError(completed["stdout"] or completed["stderr"])
    return {"summary": "cvc5 SMT-LIB probe returned sat", **completed}


def _probe_sympy() -> dict[str, Any]:
    import sympy as sp  # type: ignore[import-not-found]

    x = sp.symbols("x")
    derivative = sp.diff(x**3 + 2 * x**2 + x + 1, x)
    return {"summary": f"sympy derivative probe returned {derivative}", "derivative": str(derivative)}


def _probe_numpy() -> dict[str, Any]:
    import numpy as np

    matrix = np.array([[1.0, 2.0], [3.0, 4.0]])
    values = sorted(float(value.real) for value in np.linalg.eigvals(matrix))
    return {"summary": f"numpy eigenvalue probe returned {values}", "eigenvalues": values}


def _probe_scipy() -> dict[str, Any]:
    from scipy.optimize import minimize

    result = minimize(lambda item: (item[0] - 3.0) ** 2, [0.0], method="BFGS")
    if not result.success:
        raise RuntimeError(str(result.message))
    return {"summary": f"scipy minimize probe converged at {float(result.x[0]):.6f}", "x": float(result.x[0])}


def _probe_matplotlib() -> dict[str, Any]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with tempfile.TemporaryDirectory(prefix="haansaan-matplotlib-") as tmp:
        path = Path(tmp) / "probe.png"
        fig, ax = plt.subplots(figsize=(2, 1))
        ax.plot([0, 1], [0, 1])
        fig.savefig(path)
        plt.close(fig)
        size = path.stat().st_size
    return {"summary": f"matplotlib png probe wrote {size} bytes", "bytes": size}


def _probe_plotly() -> dict[str, Any]:
    import plotly.graph_objects as go  # type: ignore[import-not-found]

    fig = go.Figure(data=[go.Scatter(x=[0, 1], y=[0, 1])])
    html = fig.to_html(include_plotlyjs=False)
    return {"summary": f"plotly html probe produced {len(html)} chars", "char_count": len(html)}


def _probe_sklearn() -> dict[str, Any]:
    from sklearn.tree import DecisionTreeClassifier  # type: ignore[import-not-found]

    model = DecisionTreeClassifier(random_state=0)
    model.fit([[0], [1], [2], [3]], [0, 0, 1, 1])
    prediction = int(model.predict([[2]])[0])
    return {"summary": f"sklearn decision tree probe predicted {prediction}", "prediction": prediction}


def _probe_lean4() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="haansaan-lean-") as tmp:
        path = Path(tmp) / "Probe.lean"
        path.write_text("def haansaanProbe : Nat := 1\n#eval haansaanProbe + 1\n", encoding="utf-8")
        completed = _run_subprocess(["lean", str(path)], timeout_s=12)
    if completed["returncode"] != 0:
        raise RuntimeError(completed["stdout"] + completed["stderr"])
    return {"summary": "lean local probe executed", **completed}


def _probe_dafny() -> dict[str, Any]:
    source = """
method Max(a: int, b: int) returns (m: int)
  ensures m >= a && m >= b
  ensures m == a || m == b
{
  if a >= b {
    m := a;
  } else {
    m := b;
  }
}
""".strip()
    with tempfile.TemporaryDirectory(prefix="haansaan-dafny-") as tmp:
        path = Path(tmp) / "Max.dfy"
        path.write_text(source + "\n", encoding="utf-8")
        completed = _run_subprocess(["dafny", "verify", str(path)], timeout_s=15)
    if completed["returncode"] != 0:
        raise RuntimeError(completed["stdout"] + completed["stderr"])
    return {"summary": "dafny contract probe verified", **completed}


def _probe_pytest() -> dict[str, Any]:
    completed = _run_subprocess([sys.executable, "-m", "pytest", "--version"])
    if completed["returncode"] != 0:
        raise RuntimeError(completed["stdout"] + completed["stderr"])
    return {"summary": completed["stdout"].splitlines()[0] if completed["stdout"] else "pytest version executed", **completed}


def _probe_black() -> dict[str, Any]:
    completed = _run_subprocess([sys.executable, "-m", "black", "--version"])
    if completed["returncode"] != 0:
        raise RuntimeError(completed["stdout"] + completed["stderr"])
    return {"summary": completed["stdout"].splitlines()[0] if completed["stdout"] else "black version executed", **completed}


def _probe_command_version(command: str) -> dict[str, Any]:
    completed = _run_subprocess([command, "--version"])
    if completed["returncode"] != 0:
        raise RuntimeError(completed["stdout"] + completed["stderr"])
    first_line = (completed["stdout"] or completed["stderr"]).splitlines()[0]
    return {"summary": f"{command} version probe executed", "version": first_line, **completed}


def _probe_ruff() -> dict[str, Any]:
    return _probe_command_version("ruff")


def _probe_pyright() -> dict[str, Any]:
    return _probe_command_version("pyright")


def _probe_semgrep() -> dict[str, Any]:
    return _probe_command_version("semgrep")


def _probe_bandit() -> dict[str, Any]:
    return _probe_command_version("bandit")


def _probe_pip_audit() -> dict[str, Any]:
    return _probe_command_version("pip-audit")


def _probe_radon() -> dict[str, Any]:
    return _probe_command_version("radon")


def _probe_cloc() -> dict[str, Any]:
    return _probe_command_version("cloc")


SAFE_PROBES: dict[str, Callable[[], dict[str, Any]]] = {
    "z3": _probe_z3,
    "cvc5": _probe_cvc5,
    "sympy": _probe_sympy,
    "numpy": _probe_numpy,
    "scipy": _probe_scipy,
    "matplotlib": _probe_matplotlib,
    "plotly": _probe_plotly,
    "sklearn": _probe_sklearn,
    "lean4": _probe_lean4,
    "dafny": _probe_dafny,
    "pytest": _probe_pytest,
    "black": _probe_black,
    "ruff": _probe_ruff,
    "pyright": _probe_pyright,
    "semgrep": _probe_semgrep,
    "bandit": _probe_bandit,
    "pip_audit": _probe_pip_audit,
    "radon": _probe_radon,
    "cloc": _probe_cloc,
}

BUILTIN_PROBES: dict[str, Callable[[dict[str, Any], str], dict[str, Any]]] = {
    "artifact_io_builtin": _probe_artifact_io_builtin,
    "semantic_logic_builtin": _probe_semantic_logic_builtin,
    "purpose_drift_builtin": _probe_purpose_drift_builtin,
    "context_trace_builtin": _probe_context_trace_builtin,
    "memory_boundary_builtin": _probe_memory_boundary_builtin,
    "contamination_guard_builtin": _probe_contamination_guard_builtin,
    "stability_guard_builtin": _probe_stability_guard_builtin,
    "quality_management_builtin": _probe_quality_management_builtin,
    "code_review_builtin": _probe_code_review_builtin,
    "code_safety_security_builtin": _probe_code_safety_security_builtin,
    "adversarial_attack_builtin": _probe_adversarial_attack_builtin,
    "system_architecture_builtin": _probe_system_architecture_builtin,
    "complexity_level_builtin": _probe_complexity_level_builtin,
    "maintainability_builtin": _probe_maintainability_builtin,
    "innovation_builtin": _probe_innovation_builtin,
}


def _closed_completion_path() -> dict[str, Any]:
    return {
        "path_id": "HAANSAAN_CLOSED_PATH_C_V1",
        "definition": "finite non-circular path from request contract to bounded witness evidence",
        "p_is_not_a_condition": True,
        "components": [
            {
                "component_id": "request_contract",
                "stage": "CONTRACT_BOUND",
                "evidence": HAANSAAN_AGENT_CALL_REQUEST_SCHEMA_ID,
                "role": "bounded external callers submit purpose, profiles, mode, criteria, and artifacts",
            },
            {
                "component_id": "response_contract",
                "stage": "CONTRACT_BOUND",
                "evidence": HAANSAAN_AGENT_CALL_RESPONSE_SCHEMA_ID,
                "role": "machine-readable response preserves judgment and boundary fields",
            },
            {
                "component_id": "entry_label_registry",
                "stage": "CONTRACT_BOUND",
                "evidence": {"label_count": len(list_entry_labels()["labels"])},
                "role": "stable ingress labels route requests without becoming truth or completion claims",
            },
            {
                "component_id": "purpose_profile_registry",
                "stage": "CONTRACT_BOUND",
                "evidence": {"profile_count": len(PURPOSE_PROFILES)},
                "role": "purpose profiles define bounded entrypoints instead of full parallel execution",
            },
            {
                "component_id": "adapter_registry",
                "stage": "CONTRACT_BOUND",
                "evidence": {
                    "tool_count": len(TOOL_REGISTRY),
                    "builtin_probe_count": len(BUILTIN_PROBES),
                    "safe_probe_count": len(SAFE_PROBES),
                },
                "role": "adapters bind selected purposes to executable or reportable capabilities",
            },
            {
                "component_id": "selection_function",
                "stage": "IMPLEMENTED_STATIC",
                "evidence": "_select_adapter(adapter, purpose_tokens, target_tokens, criteria_tokens, allow_set)",
                "role": "finite deterministic selection by purpose axis, criteria tag, target kind, and allowlist",
            },
            {
                "component_id": "execution_modes",
                "stage": "CONTRACT_BOUND",
                "evidence": {"modes": ["plan", "check", "run"]},
                "role": "separates planning, availability inspection, and bounded execution",
            },
            {
                "component_id": "verdict_algebra",
                "stage": "CONTRACT_BOUND",
                "evidence": {"row_statuses": ["PASS", "REPORT", "FAIL"]},
                "role": "uncertainty remains REPORT instead of false PASS",
            },
            {
                "component_id": "decision_report_surface",
                "stage": "IMPLEMENTED_STATIC",
                "evidence": ["HAANSAAN_DECISION_REPORT_V1", "HAANSAAN_AGGREGATE_DECISION_REPORT_V1"],
                "role": "every selected row carries analysis, depth, improvement, direction, possible worlds, and next actions",
            },
            {
                "component_id": "construction_witness",
                "stage": "OBSERVED_RUNTIME_EVIDENCE",
                "evidence": "purpose_drift builtin vertical slice",
                "role": "request can execute through label, profile, adapter, verdict, and evidence output",
            },
        ],
        "completion_rule": {
            "rule_id": "HAANSAAN_BOUNDED_COMPLETION_RULE_V1",
            "non_circular": True,
            "if": [
                "schemas are fixed",
                "registries are finite",
                "selection is deterministic",
                "run mode executes only selected bounded probes",
                "REPORT handles missing or incomplete evidence without false PASS",
                "fixture and counterexample suites pass",
                "trace/replay/witness evidence is persisted for release gates",
            ],
            "then": "P is satisfied for the bounded haansaan core system",
            "does_not_require": [
                "external ecosystem adoption",
                "truth oracle",
                "unbounded full parallel execution",
                "all possible inputs solved",
                "current full release readiness",
            ],
        },
    }


def _non_circularity_checks(*, closed_path: dict[str, Any], witness: dict[str, Any]) -> list[dict[str, Any]]:
    rows = witness.get("tool_rows", [])
    executed_pass_rows = [
        row for row in rows
        if row.get("status") == "PASS" and row.get("executed") is True
    ]
    return [
        {
            "check_id": "p_not_embedded_in_c",
            "status": "PASS" if closed_path.get("p_is_not_a_condition") is True else "FAIL",
            "basis": "C lists fixed schemas, registries, functions, modes, verdicts, reports, and witness evidence; it does not assume P.",
        },
        {
            "check_id": "completion_claim_not_used_as_evidence",
            "status": "PASS" if witness.get("completion_claim") is False and witness.get("release_ready_claim") is False else "FAIL",
            "basis": "The witness keeps completion_claim and release_ready_claim false.",
        },
        {
            "check_id": "finite_path_components",
            "status": "PASS" if len(closed_path.get("components", [])) > 0 else "FAIL",
            "basis": f"{len(closed_path.get('components', []))} finite components are listed.",
        },
        {
            "check_id": "executed_witness_not_document_only",
            "status": "PASS" if executed_pass_rows and witness.get("fail_count") == 0 else "FAIL",
            "basis": "At least one selected builtin adapter executed and produced PASS evidence with no FAIL row.",
        },
        {
            "check_id": "bounded_not_full_parallel",
            "status": "PASS" if witness.get("all_tools_triggered") is False else "FAIL",
            "basis": "The witness selected a bounded profile path instead of triggering every adapter.",
        },
    ]


def _possibility_evidence_items(*, witness: dict[str, Any]) -> list[dict[str, Any]]:
    selected_count = int(witness.get("selected_tool_count") or 0)
    all_count = int(witness.get("all_registry_tool_count") or 0)
    return [
        {
            "item_id": "finite_state_surface",
            "status": "SATISFIED",
            "basis": {
                "profile_count": len(PURPOSE_PROFILES),
                "label_count": len(list_entry_labels()["labels"]),
                "tool_count": len(TOOL_REGISTRY),
            },
            "rejects_impossibility_axis": "finite specification impossibility",
        },
        {
            "item_id": "finite_execution_path",
            "status": "SATISFIED" if selected_count > 0 and selected_count < all_count else "UNSATISFIED",
            "basis": {
                "selected_tool_count": selected_count,
                "all_registry_tool_count": all_count,
                "all_tools_triggered": witness.get("all_tools_triggered"),
            },
            "rejects_impossibility_axis": "finite executor impossibility",
        },
        {
            "item_id": "verdict_algebra_handles_uncertainty",
            "status": "SATISFIED",
            "basis": ["PASS", "REPORT", "FAIL"],
            "rejects_impossibility_axis": "oracle requirement",
        },
        {
            "item_id": "runtime_witness_observed",
            "status": "SATISFIED" if witness.get("pass_count", 0) > 0 and witness.get("fail_count") == 0 else "UNSATISFIED",
            "basis": {
                "schema_id": witness.get("schema_id"),
                "selected_tool_ids": witness.get("selected_tool_ids"),
                "pass_count": witness.get("pass_count"),
                "fail_count": witness.get("fail_count"),
            },
            "rejects_impossibility_axis": "document-only or file-only pseudo evidence",
        },
        {
            "item_id": "boundary_no_absolute_or_release_claim",
            "status": "SATISFIED" if witness.get("completion_claim") is False and witness.get("release_ready_claim") is False else "UNSATISFIED",
            "basis": {
                "completion_claim": witness.get("completion_claim"),
                "release_ready_claim": witness.get("release_ready_claim"),
                "truth_claim": witness.get("truth_claim"),
            },
            "rejects_impossibility_axis": "false-close dependency",
        },
    ]


def _sha256_json(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dumps_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
