---
name: leaf-gui-agent
description: Reserved GUI context agent for LEAF local debugging.
---

# leaf-gui-agent

This skill is a placeholder for the GUI debugging agent.

Current allowed behavior is read-only:

- Collect HDC target metadata.
- Collect `uitest dumpLayout`.
- Collect `hilog -x`.
- Summarize page/context clues into `gui_context.json`.

Not implemented yet:

- Screenshot pull.
- Locator fallback proposal generation.
- Permission popup handling.
- Automated click or wait-condition repair.

Any future state-changing GUI action must require workflow state plus explicit approval.
