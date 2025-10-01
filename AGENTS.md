# Repository Guidelines

## Project Structure & Module Organization
The repository focuses on Linux network namespace experiments. Scripts live under `exeriments/01/` (intentional spelling) and include `ns.sh` for the linear topology and `ns_bridge.sh` for the bridge variant. Companion notes live in `exeriments/01/ns_setup_guide.md`. High-level networking references reside in `docs/` (`network.md`, `route.md`). Keep environment-specific assets or captures inside a run-specific subdirectory under `exeriments/`.

## Build, Test, and Development Commands
- `sudo bash exeriments/01/ns.sh`: Provision the three-namespace linear lab; reruns are safe because the script self-cleans first.
- `sudo bash exeriments/01/ns.sh down`: Tear down namespaces and veth pairs created by the linear lab.
- `sudo bash exeriments/01/ns_bridge.sh` / `... down`: Spin up or dismantle the bridge-based topology with leaf namespaces.
- `ip netns list` and `ip -n ns1 route`: Quick checks to confirm namespaces and routes after changes.
Prefer running scripts from the repo root so relative paths resolve.

## Coding Style & Naming Conventions
Scripts follow Bash with `#!/usr/bin/env bash` and `set -Eeuo pipefail` at the top; keep both lines. Use two-space indentation inside blocks and reserve uppercase for constant-like names (`NS1`, `V12A`). Functions remain snake_case (`cleanup`). Log output uses `[tag] message` format—match that when extending scripts. Comments are concise and precede the block they clarify; bilingual notes are acceptable if they aid operators.

## Testing Guidelines
There is no automated test harness; every change should be verified manually. After provisioning, run `ip netns exec ns1 ping -c1 10.0.23.2` and `ip netns exec ns3 ping -c1 10.0.12.1` to confirm cross-namespace reachability. For bridge scenarios, also spot-check a leaf namespace (`ip netns exec ns1a ping -c1 10.0.3.11`). Document additional probes you rely on in the relevant experiment notes.

## Commit & Pull Request Guidelines
Commits trend toward short, imperative descriptions (`add route guideline`, `clean up`). Keep the first line under 50 characters when possible; expand motivation in the body if context matters. Pull requests should link the experiment or doc they affect, summarize topology or behavior shifts, and include before/after command output when you modify scripts. Screenshots are optional; prefer terminal captures or `ip` outputs.

## Security & Permissions Tips
All setup scripts require root. Run them via `sudo` rather than logging in as root, and clean up (`down`) before switching branches to avoid orphaned namespaces. Avoid storing machine-specific credentials in version control; redact when sharing logs.
