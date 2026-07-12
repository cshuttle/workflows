# Estate engineering standards

Canonical conventions for every `cshuttle/*` homelab repo, written for humans
and coding agents alike. Each repo's root `AGENTS.md` links here and carries
only repo-specific deltas — when this file and a repo's `AGENTS.md` disagree,
the repo file wins (nearest-wins). This repo is public: standards stay
generic — no hostnames, addresses, or estate topology here.

## Change flow

- Everything of value is GitOps-tracked. Changes flow through a PR to the
  default branch; **merge to the default branch is the production event**
  (deploy automation and the documentation site key off it).
- CI must be green before merge. Squash-merge is the norm; the PR number in
  the squashed subject is the audit trail.
- Small, reviewable PRs over big-bang branches. One concern per PR.

## Linting and formatting

- **Trunk is normative.** Each repo's `.trunk/trunk.yaml` defines exactly
  which linters/formatters gate that repo; the shared Trunk CI workflow
  enforces it on PRs. Don't hand-format against the linters or add
  suppressions without a comment saying why.
- **Lefthook is the advisory local twin** (`lefthook install` per clone; base
  config in this repo under `lefthook/`). It mirrors CI but never replaces it.
- **markdownlint** runs with the shared pragmatic profile
  (`configs/markdownlint.yaml` in this repo — copy to
  `.trunk/configs/.markdownlint.yaml`): defaults on, noisy prose rules
  (line length, structural heading rules) off. Full strict adoption is
  tracked in cshuttle/workflows#7.

## Commits and PRs

- Subject: `type(scope): imperative summary` — conventional-commit types
  (`feat`, `fix`, `docs`, `ci`, `chore`, `refactor`) or a domain area as the
  prefix (e.g. `monitoring:`, `netdata:`). Lower-case, no trailing period,
  ≤72 chars.
- Body: why, not what — the diff shows what. Reference issues (`#NN`) and
  ADRs where a decision is involved.
- Agent-authored commits carry a `Co-Authored-By:` trailer identifying the
  model. Agents must not push directly to the default branch.

## Secrets

- **Runtime secrets** live in the secrets manager and are injected at run
  time (env/operator/init-container). **Git-stored secrets** are encrypted
  (`*.age` whole-file blobs, `*.sops.yaml` structured manifests) to the
  estate keypair. If it's in git it's encrypted; if a process needs it live
  it comes from the secrets manager. Nothing secret is ever committed plain.
- Never echo, log, or paste secret values — in shells, CI output, commit
  messages, or docs. Secret *references* (UUIDs, paths) are fine and must not
  be obfuscated: false-positive policy lives in the GitGuardian dashboard,
  and both CI (`ggshield-scan.yml`) and local hooks scan every change.

## Architecture decisions (ADRs)

- Decisions that constrain future work get an ADR: `docs/adr/NNNN-slug.md`
  in the repo they most affect, MADR-light format (Status / Context /
  Decision / Consequences), numbered sequentially per repo.
- Supersede rather than rewrite: a replaced ADR gets `Status: superseded by
  NNNN` and stays in place.

## Documentation

- **Docs live next to the code they describe**: each repo keeps its own
  `README.md`, `docs/`, and (where a domain vocabulary exists) a root
  `CONTEXT.md` glossary. The estate documentation site aggregates these at
  build time — a repo's docs are the source of truth, the site is a view.
- **Diagrams are code.** Mermaid blocks committed in-repo (GitHub renders
  them); richer views generated in CI from the estate architecture model
  (C4 / Structurizr DSL). No hand-drawn binary images (`.png`/`.drawio`)
  in repos.
- A PR that changes architecture (new service, moved responsibility, new
  data flow) updates the estate model / affected docs in the same change,
  or files an issue saying what drifted.
- Write for the reader who wasn't there: spell out terms on first use, use
  the repo's `CONTEXT.md` vocabulary, prefer prose + tables over walls of
  bullets.

## AGENTS.md contract

Every active repo has a root `AGENTS.md` — the canonical agent guide, read
natively by coding agents (nearest file wins in subdirectories):

- ≤ ~80 lines. One-paragraph repo purpose, then: **Commands** (build / lint /
  test, exact invocations), **Access** (how the repo touches live systems, if
  at all), repo-specific **operations**, and **Boundaries** (what must not be
  hand-edited and why).
- Links this file for everything estate-wide; duplicates nothing from it.
- `CLAUDE.md` remains as a one-line pointer to `AGENTS.md` for tools that
  look for it. Tool-specific rule files beyond that are discouraged.
- Keep it current: stale instructions are worse than none — pruning is a
  valid PR.

## Toolchain conventions

- Shell: `bash`, `set -euo pipefail`, shellcheck-clean.
- Python: ruff + black + isort (via Trunk); prefer stdlib for small tools.
- Node/TypeScript: repo-pinned toolchain (`.nvmrc` / lockfile committed);
  `typecheck`, `lint`, `build`, `test` scripts are the CI contract.
- Go: gofmt/golangci-lint (via Trunk); `make test` where a Makefile exists.
- Containers: multi-arch images pushed to the estate registry namespace;
  hadolint-clean Dockerfiles.
- Renovate keeps dependencies current; don't hand-bump what it manages —
  fix the default branch (e.g. `trunk fmt`) when its PRs fail formatting.
