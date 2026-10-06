# OpenSSF OSPS Baseline Assessment

Baseline version: v2026.08.28  
Target: Level 1  
Assessed Date: 2026-10-01  
Assessment Scope: `yaatv/yaatv` repository and release automation

## Overview

This document assesses `yaatv` against the **Open Source Project Security (OSPS) Baseline v2026.08.28** at **Level 1** ("Universal Security Floor").

Level 1 establishes the foundational security practices applicable to open-source software projects regardless of team size. Level 2 and Level 3 controls are intentionally out of scope for this assessment; yaatv operates under single-maintainer governance ([MAINTAINERS.md](../MAINTAINERS.md)) and does not claim compliance with multi-maintainer Level 2 requirements.

Compliance statuses used:
- **Met**: Requirement is satisfied with verifiable repository evidence or documented platform settings.
- **Partial**: Requirement is partially satisfied, but an operational gap or bypass privilege exists.
- **Not Met**: Requirement is currently unfulfilled.
- **N/A**: Control is not applicable to this project structure.

---

## Level 1 Controls Evaluation

| Control | Name & Summary | Status | Evidence | Follow-up |
| --- | --- | --- | --- | --- |
| **OSPS-AC-01.01** | Multi-Factor Authentication | **Met** | GitHub-hosted setting. GitHub enforces mandatory two-factor authentication (2FA) for all contributors and repository maintainers. | Ensure any newly onboarded maintainer accounts maintain active 2FA. |
| **OSPS-AC-02.01** | Collaborator Permissions Default | **Met** | GitHub-hosted setting. GitHub repository access requires explicit invitation and manual role assignment (Read, Triage, Write, Admin). No broad default write access is granted. | Periodically audit collaborator and team permission assignments. |
| **OSPS-AC-03.01** | Primary Branch Direct Commit Prevention | **Partial** | Pull request review and status check workflows are configured on `main`. However, repository maintainers retain administrator bypass privileges allowing direct commits and unreviewed merges. | Configure a GitHub repository ruleset on `main` that disables bypass authority for all roles, including administrators, to enforce strict branch immutability. |
| **OSPS-AC-03.02** | Primary Branch Deletion Protection | **Met** | GitHub-hosted setting. `main` is configured as the repository's default branch; GitHub prohibits deletion of the designated default branch. | Maintain `main` as the default branch. |
| **OSPS-BR-01.01** | CI/CD Untrusted Metadata Sanitization | **Met** | Workflow files (`.github/workflows/ci.yml`, `codeql.yml`, `release.yml`, `scorecard.yml`). Workflows do not interpolate untrusted event metadata (e.g., issue or PR body text) directly into shell commands. Scripts use structured Python invocations and argument vectors. | Review newly introduced workflow inputs for shell injection risks in future pull requests. |
| **OSPS-BR-01.03** | Privileged Credential Protection in CI/CD | **Met** | PR builds execute under `pull_request` triggers where GitHub Actions restricts repository secrets from fork contexts. Any configured production release secrets (`PGP_PRIVATE_KEY`, optional `PGP_PASSPHRASE`) are consumed only by the `environment: release` job. That job runs only for version tags (`refs/tags/v*`) and fails if the private key is absent or does not match `public.key`. | Configure the release environment with the signing secrets, publish the signing fingerprint out of band when rotating keys, and maintain environment protection rules. |
| **OSPS-BR-03.01** | Encrypted Official Project Channels | **Met** | `README.md`, `pyproject.toml`. All official communication and project URIs use encrypted transport exclusively (`https://yaatv.org`, `https://convert.yaatv.org`, `https://github.com/yaatv/yaatv`). | Reject non-HTTPS links in documentation and source headers. |
| **OSPS-BR-03.02** | Authenticated Distribution Channels | **Met** | Releases are distributed through authenticated HTTPS channels: GitHub Releases (`https://github.com/yaatv/yaatv/releases`) and PyPI (`https://pypi.org/project/yaatv/`). The release workflow requires a detached PGP signature for `SHA256SUMS` and retains Sigstore build provenance attestations. | Maintain the published release key and build attestations on future releases. |
| **OSPS-BR-07.01** | Prevention of Sensitive Data in VCS | **Met** | `.gitignore` excludes local environment files (`.env`, `.env.*`, `.envrc`, with `.env.example` allowed), caches, credentials, and scratch directories. Pre-release quality gate runs Bandit security scanning (`scripts/check.py`). CodeQL scanning runs weekly and on pull requests. | Consider adding automated pre-commit secret detection (e.g. `gitleaks`) to complement static audits. |
| **OSPS-DO-01.01** | User Documentation for Basic Functionality | **Met** | `README.md` provides installation instructions, command examples, aspect ratio/canvas options, background blur/image usage, and troubleshooting guidance. Browser conversion web application available at `convert.yaatv.org`. | Keep CLI documentation synchronized as flags evolve. |
| **OSPS-DO-02.01** | Defect Reporting Guidelines | **Met** | `.github/ISSUE_TEMPLATE/bug_report.yml` provides a structured template for defect reporting, and `CONTRIBUTING.md` outlines bug report expectations. | None. |
| **OSPS-GV-02.01** | Public Discussion Channels | **Met** | GitHub Issues and GitHub Pull Request review threads are enabled and publicly accessible for feature proposals, bug discussions, and design reviews. | Continue handling architectural discussions through public issues and PRs. |
| **OSPS-GV-03.01** | Contribution Process Documentation | **Met** | `CONTRIBUTING.md` details development prerequisites, test workflows, coding conventions, and the Contributor Attribution and Merge Policy. | None. |
| **OSPS-LE-02.01** | OSI/FSF Approved Source Code License | **Met** | `LICENSE` and `pyproject.toml`. The repository is licensed under the GNU General Public License v2.0 or later (`GPL-2.0-or-later`), recognized by both the Open Source Initiative (OSI) and Free Software Foundation (FSF). | None. |
| **OSPS-LE-02.02** | OSI/FSF Approved Release Asset License | **Met** | Release ZIP archives bundle `LICENSE`, `SOURCE.txt`, `THIRD_PARTY_LICENSES.txt`, and `FFMPEG_BUILD_INFO.txt`. Each onefile executable embeds those notice files as bundled data. | Ensure the third-party license generator and notice embedding run in all binary release builds. |
| **OSPS-LE-03.01** | License File in Source Repository | **Met** | `LICENSE` file is located at repository root. | None. |
| **OSPS-LE-03.02** | License File in Released Software Assets | **Met** | `.github/workflows/release.yml` includes license, third-party, FFmpeg build, and source notices in portable ZIPs and embeds them in each onefile executable. | Keep notice generation and embedding in all binary release builds. |
| **OSPS-QA-01.01** | Public Static Source Code URL | **Met** | Source code is hosted publicly at static URL `https://github.com/yaatv/yaatv`. | None. |
| **OSPS-QA-01.02** | Publicly Readable Change History | **Met** | Complete Git commit history, commit authorship, timestamps, and pull request histories are publicly readable on GitHub. | Preserve author attribution during squash merges in accordance with project policy. |
| **OSPS-QA-02.01** | Direct Language Dependency Manifest | **Met** | `pyproject.toml` declares all direct runtime dependencies under `[project.dependencies]` (`mutagen`, `Pillow`) and development tools under `[project.optional-dependencies]`. | Maintain minimal runtime dependencies as defined in `AGENTS.md`. |
| **OSPS-QA-04.01** | Multi-Repository Codebase Documentation | **N/A** | `yaatv` is a single-repository project. There are no external sub-repositories or multi-codebase components. | If sub-repositories are created in the future, document them in project governance. |
| **OSPS-QA-05.01** | No Generated Executable Artifacts in VCS | **Met** | `.gitignore` excludes `dist/`, `build/`, `*.exe`, `yaatv-linux`, and release archives. `AGENTS.md` boundaries prohibit committing binaries or compiled executables. Repository tree audit confirms zero executable artifacts present. | None. |
| **OSPS-QA-05.02** | No Unreviewable Binary Artifacts in VCS | **Met** | `.gitignore` excludes binary blobs. Media assets in `docs/docs-assets/` are limited to documentation images. No unreviewable binaries exist in source trees. | Maintain strict review on asset additions. |
| **OSPS-VM-02.01** | Published Security Contacts | **Met** | `SECURITY.md` specifies private vulnerability reporting via GitHub Security Advisories (`https://github.com/yaatv/yaatv/security/advisories/new`) and lists direct maintainer contact information (`@cavyion`). | None. |

---

## Gap Analysis & Observations

1. **Primary Branch Enforcement (`OSPS-AC-03.01`)**:
   - Status: **Partial**.
   - Details: While pull requests and automated status checks are the standard operating procedure for `main`, repository maintainers have bypass rights enabled on the hosting platform. Full compliance requires setting up a GitHub ruleset that disallows bypassing branch protection rules for all roles including repository administrators.

2. **Governance Ceiling**:
   - yaatv is intentionally assessed against **Level 1** only. Higher maturity levels (Level 2+) mandate multi-maintainer consensus, formal secondary maintainer roles, and independent review sign-offs before merge. At present, yaatv is maintained by a single primary maintainer, making Level 2 unattainable without changes to governance structure.
