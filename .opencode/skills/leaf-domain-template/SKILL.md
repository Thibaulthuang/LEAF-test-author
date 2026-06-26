---
name: leaf-domain-template
description: Template for adding a LEAF domain skill. Copy this structure for new domains.
---

# leaf-domain-template

Use this template when adding a new `leaf-<domain>` skill.

## Domain Defaults

- Platform default: `openharmony` unless the domain explicitly needs another platform.
- Define the target app or target feature ownership.
- State whether the target app is built in or provided by the user.
- State which actions are read-only and which actions mutate device state.

## Semantic Step Expansion

Define how natural user phrases become explicit ordered domain operations.
Do not rely on punctuation splitting. A short phrase must expand into a complete
end-to-end plan when the domain requires evidence.

Example shape:

```json
{
  "target_feature": "<domain>.<feature>",
  "steps": [
    "打开目标功能",
    "执行核心动作",
    "验证真实证据"
  ],
  "risk": "真实执行时可能改变设备状态",
  "confirmation_required": true
}
```

## Plan Input Contract

The OpenCode agent writes `.leaf/runs/<run_id>/plan_input.json` before calling
the deterministic Python layer. The Python layer must validate:

- `target_feature`
- non-empty ordered `steps`
- required evidence steps
- risk wording when real execution mutates device state

## Quality Gates

Define domain-specific gates and what each gate proves. Keep draft gates separate
from real-device gates.

- `<DOMAIN>_DIRECT_SMOKE_PASS`: framework/device control evidence.
- `<DOMAIN>_E2E_PASS`: business behavior evidence.
- `<DOMAIN>_REAL_PASS`: real-device system-app execution evidence.

## Required Python Touchpoints

Adding a domain normally requires reviewing these files:

- `python3 -m tools.leaf_author extension-contract <domain>`: export the
  framework extension manifest and check missing domain/runtime hooks.
- `python3 -m tools.leaf_author validate-extension-contract <domain>`: fail
  fast when a domain is missing required registry hooks.
- `tools/leaf_author/domain_registry.py`: register the domain contract for
  target feature inference, semantic plan validation, and action mapping.
- `tools/leaf_author/runtime_registry.py`: register real-device runtime modes
  such as `direct_smoke` or `capture_e2e` when the domain has executable
  system-app evidence. Also register the runtime artifact keys, pass quality
  gates, confidence, and review notes consumed by experience recording and team
  manifests. Report quality-gate priority should come from this registry, not
  from report-layer domain branches.
- `tools/leaf_author/<domain>_smoke.py`: domain preflight/direct/e2e execution if needed.
- `tests/`: unit tests for plan validation, generated drafts, quality gates, and CLI output.

Avoid adding new domain branches to core workflow orchestration. The workflow
state machine, phase contract, report surfaces, and context manifests should
remain domain-neutral. Domain-specific behavior enters through the registry,
domain skill, runtime registry, optional runtime smoke module, and reviewable
quality-gate artifacts.

## Safety Rules

- Do not run device-mutating commands before plan confirmation.
- Require a second confirmation before destructive or state-changing real-device execution.
- GUI context collection must remain read-only unless a separate workflow state and user approval authorize mutation.
- Experience records are reviewable draft knowledge and must not auto-modify AW code.
