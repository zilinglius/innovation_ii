# Repository Guidelines

## Project Structure & Module Organization
The labs live under `exeriments/01/` (spelling intentional). `ns.sh` provisions a five-namespace ring, while `ns_bridge.sh` builds the bridge-centric topology described in `README.md`. Shared background material sits in `docs/`, and setup details stay in `exeriments/01/ns_setup_guide.md`. Keep new lab scripts beside their documentation so runnable artifacts and references stay synchronized.

## Build, Test, and Development Commands
Run labs from the repo root with elevated privileges: `sudo bash exeriments/01/ns.sh` or `sudo bash exeriments/01/ns_bridge.sh`. Each script supports teardown with the `down` argument, e.g., `sudo bash exeriments/01/ns.sh down`. Use `bash -n <script>` for syntax checks and `shellcheck <script>` for static linting before committing. When experimenting, capture namespace state with `ip netns list` and `ip -n <ns> addr` for inclusion in notes or PRs.

## Coding Style & Naming Conventions
Scripts use Bash with `set -Eeuo pipefail`; mirror that guard block in new files. Constants and interface names stay uppercase with descriptive prefixes (`V12A`, `LAN_L_GW`), while helper functions use lowercase snake case (`exists_ns`). Indent bodies with two spaces to match existing formatting. Inline comments mix concise English with targeted Chinese explanations—either language is acceptable, but keep comments short and operational.

## Testing & Verification Guidelines
There is no automated CI; rely on repeatable manual checks. After provisioning, ensure namespaces respond with targeted pings (see `README.md` for reference pairs) and confirm forwarding via `ip netns exec <ns> sysctl net.ipv4.ip_forward`. For coverage-like assurance, document at least one successful round-trip per new link or bridge you introduce. Record troubleshooting steps in commit or PR notes so other contributors can replay them.

## Commit & Pull Request Guidelines
Recent commits use brief, verb-led subjects in lowercase (e.g., `clean up`, `add route guideline`). Follow that style and keep subjects under 65 characters. In pull requests, include: 1) a one-paragraph summary of topology or documentation changes, 2) the exact commands executed (provision, tear-down, lint), and 3) any captures (`ip` output, ping results, tcpdump snippets) relevant to reviewers. Reference linked issues when available and note regressions explicitly, even if they are expected during a draft.
