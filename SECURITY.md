# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | Yes |

## Reporting a vulnerability

Please do **not** open a public issue for security problems. Use GitHub's private
vulnerability reporting ("Report a vulnerability" under the repository's Security
tab). Include the version, a description, reproduction steps and the impact.

We aim to acknowledge reports within 7 days and to agree on a disclosure timeline
with you.

## Scope

In scope: command execution policy bypasses, merges or pushes without approval,
destructive git operations, credential leakage into logs/reports/database, path
traversal, and injection through agent output, plans or repository content.

Out of scope: actions an agent can perform with the user's own OS permissions (a git
worktree is documented as not being a sandbox), and vulnerabilities in provider CLIs
themselves (report those to the provider).

See [docs/security.md](docs/security.md) for the security model.
