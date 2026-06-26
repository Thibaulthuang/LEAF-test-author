from __future__ import annotations


_DEFAULT_SCOPE = "system_app_only"
_DEFAULT_FORBIDDEN_TERMS = ["hap", "test hap", "app hap", "install_hap", "build_app_and_test"]


def default_target_policy() -> dict[str, object]:
    return {
        "scope": _DEFAULT_SCOPE,
        "forbidden_terms": list(_DEFAULT_FORBIDDEN_TERMS),
    }


def build_target_policy_contract() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "manifest_kind": "leaf_target_policy",
        "target_policy": default_target_policy(),
        "usage": {
            "phase_decisions": "tools.leaf_author.phase_contract",
            "phase_guard": "tools.leaf_author.phase_guard",
            "real_device_gates": "tools.leaf_author.real_device_contract",
            "reports": "tools.leaf_author.reports",
            "batch_handoff": "tools.leaf_author.batch_registry",
        },
    }


def target_policy_from_contract(contract: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(contract, dict):
        return default_target_policy()
    return normalize_target_policy(contract.get("target_policy"))


def normalize_target_policy(policy: object) -> dict[str, object]:
    if not isinstance(policy, dict):
        return default_target_policy()
    scope = str(policy.get("scope") or _DEFAULT_SCOPE)
    terms = policy.get("forbidden_terms")
    if not isinstance(terms, list):
        terms = _DEFAULT_FORBIDDEN_TERMS
    normalized_terms = [str(term).lower() for term in terms if str(term)]
    if not normalized_terms:
        normalized_terms = list(_DEFAULT_FORBIDDEN_TERMS)
    return {
        "scope": scope,
        "forbidden_terms": normalized_terms,
    }


def target_policy_forbidden_terms(policy: object) -> list[str]:
    normalized = normalize_target_policy(policy)
    return [str(term) for term in normalized["forbidden_terms"]]


def with_target_policy(decision_contract: dict[str, object], target_policy: object | None = None) -> dict[str, object]:
    policy_source = target_policy if target_policy is not None else decision_contract.get("target_policy")
    return {**decision_contract, "target_policy": normalize_target_policy(policy_source)}


def is_system_app_only_target_policy(policy: object) -> bool:
    return normalize_target_policy(policy).get("scope") == _DEFAULT_SCOPE
