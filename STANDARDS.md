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

## Releases and versioning

- **Versions are `vMAJOR.MINOR.PATCH`.** A **major** means a consumer must act:
  for a library or shared CI definition, that the caller must change something;
  for a deployed application, that the release cannot go out by the normal
  automated path alone (migration, new env var or secret, changed route,
  manifest edit). Minor is a capability someone would notice; patch is the rest.
- **Released tags are immutable and are never moved**, and no floating major
  tag is published. Supersede a bad release with a patch. Anything consumed by
  reference — shared workflows, shared hook configs — is pinned to an exact
  tag by its consumers, never to a branch.
- **Build once, promote.** A release re-tags the artifact that CI already built
  and tested for that commit; it does not rebuild it. Rebuilding on a tag ships
  a different artifact from the one that was tested.
- **Deployments track released versions, gated at majors** — automation carries
  minors and patches, a major waits for a human. Rolling back is a *constraint*
  change (narrow the allowed range), not a value change: reverting a pinned
  version alone is undone by the next reconcile.
- **Cutting a release is a deliberate act with a human-chosen version**, not an
  inference from commit messages. Release notes are generated, with an optional
  hand-written summary above them; no changelog file to keep honest.
- Rationale and the rejected alternatives: `docs/adr/0001-release-and-versioning-model.md`
  in this repo.

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
  bullets (a how-to's numbered steps are the exception, below).

### Kinds of human doc

These rules cover docs written for people. Agent-facing files (`AGENTS.md`,
`CLAUDE.md`, skills, `docs/agents/`) follow the AGENTS.md contract below.
`CONTEXT.md` keeps its own glossary format.

| Kind | What it is | Where it lives |
|---|---|---|
| **Guide** | A page with exactly one [Diátaxis](https://diataxis.fr/) type | `docs/tutorials/`, `docs/how-to/`, `docs/reference/`, `docs/explanation/` |
| **Record** | A log of what was decided, found or planned: ADR, research note, spec, changelog | `docs/adr/`, `docs/research/`, `docs/specs/`, `CHANGELOG.md` |
| **Landing page** | The repo's `README.md`: what the repo is, how to start, links to the guides | repo root |

The four guide types:

| Type | The reader wants to | Example |
|---|---|---|
| Tutorial | Learn by doing, start to finish | "Your first deploy" |
| How-to | Do one task they already understand | "Restore a guest from backup" |
| Reference | Look up a fact | A table of settings, ports or commands |
| Explanation | Understand why | How the backup chain works and why |

- **One page, one type.** A how-to that needs a long "why" links to an
  explanation page instead of holding it.
- **"How-to" is the only name for a task guide.** Do not start new
  `*-runbook.md` files.
- Records keep their own formats (the ADR format above) and get no type.

### Writing rules

New human docs, guides and records alike, follow the writing rules of
ASD-STE100 Simplified Technical English. The approved-word dictionary is
not used: tool names and technical terms stay as they are.

1. A step is 20 words or fewer. Any other sentence is 25 words or fewer.
2. One instruction per sentence. One topic per paragraph, six sentences
   or fewer.
3. Write a step as a command: "Run `make test`", not "You should run the
   tests".
4. Use the active voice: "The job deletes the file", not "The file is
   deleted".
5. Use one word for one thing. Explain a new term where it first appears.
6. Number the steps of a procedure. Put a warning before the step it is
   about, not after it.
7. Keep code, paths, commands and output exactly as they are.

### Adoption

- A new doc follows these rules from its first commit.
- An existing doc follows them after its next large edit. In that same PR,
  move it into its type folder and fix the links that point to it. Leave
  no stub at the old path.
- Code review checks the rules. Add a prose linter only if review keeps
  catching the same mistake.

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
