# Releasing

AgentBridge publishes two packages to PyPI from one tag:

| PyPI project | Built from |
|---|---|
| `agentbridge-core` | repository root (`pyproject.toml`) |
| `agentbridge-bench` | `packages/agentbridge-bench/` (wheel only: it bundles `benchmarks/`) |

Publishing uses [trusted publishing](https://docs.pypi.org/trusted-publishers/): GitHub
Actions proves its identity to PyPI with a short-lived OIDC token. No PyPI password or
API token is stored in the repository or in GitHub secrets.

## One-time setup (maintainer)

1. Sign in to PyPI with an account that has two-factor authentication enabled.
2. Open **Your account → Publishing → Add a new pending publisher** and add it
   **twice**, once per project:

   | Field | `agentbridge-core` | `agentbridge-bench` |
   |---|---|---|
   | Owner | `yoonjae26` | `yoonjae26` |
   | Repository name | `AgentBridge` | `AgentBridge` |
   | Workflow name | `release.yml` | `release.yml` |
   | Environment name | `pypi` | `pypi-bench` |

   PyPI rejects two pending publishers with an identical configuration, which is why
   each package has its own environment.

3. In GitHub: **Settings → Environments → New environment**, create `pypi` and
   `pypi-bench`. Optionally add yourself as a required reviewer so every upload waits
   for your click.

A pending publisher becomes a normal one after the first successful upload.

## Cutting a release

1. Set the same version in `pyproject.toml`, `packages/agentbridge-bench/pyproject.toml`,
   `src/agentbridge/__init__.py` and `packages/agentbridge-bench/src/agentbridge_bench/__init__.py`.
2. Move the `Unreleased` notes in `CHANGELOG.md` under the new version.
3. Commit, then tag and push:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

The `release` workflow checks that the tag matches both versions, builds and
smoke-tests the wheels in a clean environment, uploads them to PyPI and creates the
GitHub release. PyPI versions are immutable: a published version can never be
re-uploaded, so a broken release needs a new version number.
