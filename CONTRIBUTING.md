# Contributing to AI-IOS

## Prerequisites

- Python 3.13+ and [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+ and `pnpm`
- Docker and Docker Compose

## Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Production-ready code only |
| `develop` | Integration branch for the next release |
| `feature/*` | New functionality, branched from `develop` |
| `bugfix/*` | Non-urgent fixes, branched from `develop` |
| `release/*` | Release stabilization, branched from `develop` |
| `hotfix/*` | Urgent production fixes, branched from `main` |

## Commit Message Convention

This repository follows [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, `security`, `ci`.

Example: `feat(gateway): add liveness and readiness endpoints`

## Pull Request Process

1. Branch from `develop` (or `main` for hotfixes) using the naming convention above.
2. Ensure Ruff, Black, MyPy, Bandit, ESLint, and Prettier all pass locally.
3. Ensure all tests pass with the coverage target defined for the module you changed.
4. Open a PR against `develop` using the pull request template.
5. At least one review approval and a green CI run are required before merge.

## Known Environment Issues

On Windows machines with a corporate Application Control policy (e.g. WDAC),
some tools' compiled/native components may be blocked from loading even
though the tools install successfully:

- `black` and `mypy` may fail with `An Application Control policy has
  blocked this file` when invoked via their console-script `.exe` entry
  points or when importing a native dependency (observed with `mypy`'s
  `librt` dependency). This does not affect Linux — CI and Docker builds are
  unaffected. There is no code-level workaround; treat CI as the source of
  truth for these checks when this occurs locally.
- `uvicorn`'s console-script entry point may be similarly blocked. Use
  `uv run python -m uvicorn main:app` instead of `uv run uvicorn main:app` as
  a workaround — invoking the module directly avoids the blocked launcher.
- `pip-audit` (and other `requests`-based tools) may fail TLS verification
  behind a corporate TLS-inspecting proxy. The workspace's `pip-system-certs`
  dev dependency patches Python's SSL trust store to use the OS certificate
  store and resolves this once installed (`uv sync`).
- If `uv`'s own network calls fail with a certificate error, pass
  `--system-certs` (e.g. `uv sync --system-certs`).
- Native Windows (no WSL) typically has no `make`. Either install it (e.g.
  via `choco install make` or use WSL), or run the commands inside the
  `Makefile` targets directly — each one is a single, already-documented
  `uv`/`pnpm`/`docker` command.

## Coding Standards

All code must comply with
[`docs/005_Coding_Standards_Master.md.txt`](docs/005_Coding_Standards_Master.md.txt).
This is non-negotiable: SOLID, Clean Architecture, Repository Pattern, strong
typing, async-first, no hardcoded configuration, no placeholder or TODO code
in anything merged to `develop` or `main`.
