---
name: ezwin-e2e
description: Execute EzWinCommand real-environment validation across Android emulator or device, ADB, Windows Server, Web administration, LAN pairing, media/Core Audio, UAC, or firewall behavior. Use only when actually driving these environments, not when merely discussing a test plan.
---

# EzWinCommand E2E Runbook

Prove one user-visible path end to end with a traceable chain from action to UI, network, and Server or Windows effect. This Skill supplies project-specific execution reference; it does not create a verifier role or release gate.

## 1. Pin the environment

Record the Windows version, Android API/device, build identity, Server address and relevant configuration. Redact pairing codes, Bearer tokens, device keys and Server identity material.

Choose an address the active client can reach. Android Emulator reaches the host through `10.0.2.2`; `127.0.0.1` inside the emulator is the emulator itself. ADB reverse or a trusted-LAN address is valid when it matches the scenario.

Completion criterion: the chosen client reaches `/ping`, and the recorded environment is sufficient to reproduce that route.

## 2. Establish the observable chain

Start only the services the scenario needs. Long-running Server, emulator, log stream or watcher processes use OMP `hub` process operations so their readiness and logs remain inspectable.

For Android interaction, locate controls in this order:

1. `resource-id`
2. `content-desc`
3. visible text plus parent relationship
4. coordinates only when no semantic target exists

Refresh the UI hierarchy after navigation, keyboard changes, scrolling or recomposition. After text input, read the field back before submitting.

Observe the Server access log or relevant endpoint after each decisive UI action. If no request arrived, classify the failure as fixture or interaction setup before investigating product code.

Completion criterion: every decisive action has an observable downstream event, or the first broken link is identified.

## 3. Exercise the target behavior

Cover the named happy path and only the failure or recovery paths material to the change. Typical surfaces are:

- Web management creates the pairing code and manages devices.
- Android enters the reachable address, pairs, authenticates and reaches the control surface.
- Server receives the expected authenticated request and returns the documented wire result.
- Windows command, media or Core Audio behavior produces the intended host effect.

For cross-endpoint changes, verify both producer and consumer. For media and audio, distinguish metadata/control state from actual host playback or endpoint switching.

Completion criterion: observed behavior matches the user-visible acceptance condition, including material recovery behavior.

## 4. Capture evidence

Report each check with:

- **Mode:** Automated | AI-assisted | Manual
- **Environment:** redacted identifiers and reachability route
- **Action:** reproducible input and interaction
- **Expected:** the observable contract
- **Actual:** what happened
- **Evidence:** command output, HTTP result, structured UI dump, screenshot path or redacted log range

Use `Manual — 待人工验证` for a path not executed. Never convert an unexecuted step into a pass. Screenshots, UI dumps, logs and temporary reports are session evidence, not formal project documentation.

Completion criterion: another engineer can distinguish what was executed, what passed or failed, and what remains unverified without inferring from prose.

## 5. Finish safely

Restore reversible fixture changes and stop processes started for the check. Do not reset unrelated device, application or user state. Report any state intentionally left running.

Completion criterion: the test environment is either restored or its remaining state is explicitly listed.
