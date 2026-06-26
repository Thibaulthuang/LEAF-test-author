from __future__ import annotations

from pathlib import Path

from tools.leaf_author.target_policy import default_target_policy


_COMMANDS = {
    "leaf-new-case.md": ["/leaf-new-case", "leaf-test-author", "workflow.json", "plan.json"],
    "leaf-resume.md": ["/leaf-resume", "leaf-test-author", "resume", "--auto-safe"],
    "leaf-batch.md": ["/leaf-batch", "leaf-test-author", "report-batch", "resume-batch"],
    "leaf-report.md": ["/leaf-report", "leaf-test-author", "report-run", "audit-run"],
}
_SKILLS = {
    "leaf-test-author": ["workflow.json", "context_manifest", "target_policy", "user_loop", "phase-guard", "agent-handoff-contract"],
    "leaf-camera": ["system Camera", "real-device", "confirmation", "Camera", "UiTest"],
    "leaf-gui-agent": ["read-only", "uitest dumpLayout", "hilog", "workflow"],
    "leaf-domain-template": ["domain", "openharmony"],
}
_CONTRACT_SOURCES = [
    "workflow.json",
    "docs/workflow-contract.json",
    "phase-guard",
    "target-policy",
    "agent-handoff-contract",
    "real-device-contract",
    "runtime-registry-contract",
    "runtime-evidence-contract",
    "runtime-mode-only-open-code-entrypoints",
]
_OPEN_CODE_FORBIDDEN_RUNTIME_FLAGS = {
    "--camera-direct": "must use --runtime-mode instead of legacy --camera-direct",
    "--camera-capture": "must use --runtime-mode instead of legacy --camera-capture",
}
_RUNTIME_MODE_REQUIRED_TERMS = ["--runtime-mode direct_smoke", "--runtime-mode capture_e2e"]


def validate_opencode_contract(root: Path | None = None) -> dict[str, object]:
    repo_root = root or Path(".")
    issues: list[str] = []
    command_count = _validate_commands(repo_root, issues)
    skill_count = _validate_skills(repo_root, issues)
    return {
        "schema_version": "1.0",
        "manifest_kind": "leaf_opencode_contract_guard",
        "status": "stable" if not issues else "unstable",
        "issues": issues,
        "exit_code": 0 if not issues else 1,
        "command_count": command_count,
        "skill_count": skill_count,
        "required_skills": sorted(_SKILLS),
        "contract_sources": list(_CONTRACT_SOURCES),
        "target_policy": default_target_policy(),
    }


def _validate_commands(root: Path, issues: list[str]) -> int:
    commands_dir = root / ".opencode" / "commands"
    count = 0
    for filename, required_terms in _COMMANDS.items():
        path = commands_dir / filename
        rel = f".opencode/commands/{filename}"
        if not path.is_file():
            issues.append(f"{rel}: command file is missing")
            continue
        count += 1
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for term in required_terms:
            if term.lower() not in lowered:
                if term == "leaf-test-author":
                    issues.append(f"{rel}: must invoke leaf-test-author")
                else:
                    issues.append(f"{rel}: missing required contract term {term!r}")
        _validate_runtime_mode_entrypoint_text(rel, text, issues)
        if "python3 -m tools.leaf_author new-case" in lowered and "leaf-test-author" not in lowered:
            issues.append(f"{rel}: must not expose Python new-case as the user-facing owner")
    return count


def _validate_skills(root: Path, issues: list[str]) -> int:
    skills_dir = root / ".opencode" / "skills"
    count = 0
    for skill_name, required_terms in _SKILLS.items():
        path = skills_dir / skill_name / "SKILL.md"
        rel = f".opencode/skills/{skill_name}/SKILL.md"
        if not path.is_file():
            issues.append(f"{rel}: skill file is missing")
            continue
        count += 1
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for term in required_terms:
            if term.lower() not in lowered:
                issues.append(f"{rel}: missing required contract term {term!r}")
        _validate_runtime_mode_entrypoint_text(rel, text, issues)
    return count


def _validate_runtime_mode_entrypoint_text(rel: str, text: str, issues: list[str]) -> None:
    for flag, message in _OPEN_CODE_FORBIDDEN_RUNTIME_FLAGS.items():
        if flag in text:
            issues.append(f"{rel}: {message}")
    if rel.endswith("leaf-new-case.md") or rel.endswith("leaf-test-author/SKILL.md") or rel.endswith("leaf-camera/SKILL.md"):
        for term in _RUNTIME_MODE_REQUIRED_TERMS:
            if term not in text:
                issues.append(f"{rel}: missing required runtime mode command {term!r}")
