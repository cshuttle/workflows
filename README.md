# workflows

Shared **CI definitions** for the `cshuttle` homelab estate: reusable GitHub
Actions workflows (`.github/workflows/`) and the shared **Lefthook** git-hook
config (`lefthook/`).

This repo is intentionally **public** so the private GitOps repos can consume it
— cross-repo reusable workflows between *private* repos require a paid GitHub
plan, but a public host is callable by any repo on any plan, and Lefthook
`remotes:` likewise pull from here. Only generic CI recipes live here; no
secrets, manifests, or hostnames.

## Available workflows

### `kustomize-validate.yml`

Renders every `kustomization.yaml` root in the caller's checkout with
`kustomize build --enable-helm` and schema-validates the output with
`kubeconform`. Catches a commit that breaks a render before ArgoCD pulls it.

```yaml
# .github/workflows/validate.yml in a GitOps content repo
name: validate
on:
  push:
  pull_request:
jobs:
  kustomize:
    uses: cshuttle/workflows/.github/workflows/kustomize-validate.yml@main
```

Optional input `paths` (space-separated roots to scan; default `.`).

### `ggshield-scan.yml`

Runs a GitGuardian [`ggshield`](https://github.com/GitGuardian/ggshield) secret
scan over the caller's pushed/PR commit range — a **pre-merge** gate, unlike the
GitGuardian GitHub App which only flags leaks retroactively. Findings also appear
in the shared GitGuardian dashboard (where policy and false-positives — e.g. bws
UUIDs — are managed; don't obfuscate them in code).

```yaml
# .github/workflows/ggshield.yml in any repo
name: ggshield
on:
  push:
  pull_request:
jobs:
  ggshield:
    uses: cshuttle/workflows/.github/workflows/ggshield-scan.yml@main
    secrets: inherit
```

Requires the org Actions secret **`GITGUARDIAN_API_KEY`** (scope `scan`; source
of truth in bws Infrastructure). `secrets: inherit` passes it through — no
per-repo secret needed.

### `komodo-deploy.yml`

Triggers a Komodo stack deploy from CI — for **self-building stacks** (repos
whose CI builds the ghcr image the stack runs). Git-push webhooks race the
async image build and the `auto_update` digest poll lags by minutes; this
workflow fires *after* the image push succeeds, POSTing a push-shaped,
HMAC-signed payload to the stack's existing Komodo deploy listener. No Komodo
API key involved — it uses the same shared webhook secret a GitHub push hook
would.

```yaml
# final job in the repo's build workflow
deploy:
  needs: build            # gate on the image push having succeeded
  if: github.ref == 'refs/heads/main'
  uses: cshuttle/workflows/.github/workflows/komodo-deploy.yml@main
  with:
    stack-id: <24-hex komodo stack id>
    listener-base: https://<komodo webhook listener host>
    runner: arc-<repo>
  secrets:
    KOMODO_WEBHOOK_SECRET: ${{ secrets.KOMODO_WEBHOOK_SECRET }}
```

Requires the org Actions secret **`KOMODO_WEBHOOK_SECRET`** (Komodo Core's
shared webhook HMAC secret; source of truth in bws "Komodo GitHub Webhook
Secret") granted to the caller repo. `listener-base` is required by design —
this repo is public and carries no estate hostnames. Fire-and-forget: the
listener 200s and processes async, so keep the stack's `auto_update = true`
as the backstop. Background: cshuttle/Topology#23 (this fallback) and
cshuttle/Komodo#120 (the estate-wide `registry_package` router it stands in
for).

### `mirror-image.yml`

Copies an upstream container tag into a ghcr.io repo you control, so CI pulls
from a well-peered registry instead of a badly-peered one.

Registry throughput varies enormously by peering, and a badly peered one is not
merely slow — it fails. Measured from one homelab site against the same 926MB
image: **ghcr.io 192 MB/s, docker.io 86, quay.io 79, registry.k8s.io 20,
mcr.microsoft.com 2.2**. That one registry was 391s of a ~640s CI job, and its
sibling CDN blew a 30s client timeout under load and failed builds outright.
Mirroring took the job to ~80s.

```yaml
# .github/workflows/mirror-<image>.yml in the consuming repo
on:
  workflow_dispatch:
  schedule:
    - cron: "17 4 * * 1"        # weekly re-sync; a no-op unless upstream moved
jobs:
  mirror:
    uses: cshuttle/workflows/.github/workflows/mirror-image.yml@main
    permissions:
      contents: read
      packages: write
    with:
      source: mcr.microsoft.com/playwright
      destination: ghcr.io/${{ github.repository_owner }}/playwright
      tag: v1.61.1-noble
      runner: arc-<repo>
```

**Measure before adopting it.** A mirror only helps if the pull is genuinely the
bottleneck — compare the pull's *download* phase against its *extract* phase
first (docker logs both; extraction was 8s of that 400s). Raising runner
concurrency against a starved path makes things worse, not better.

Notes:

- **Skips the copy when the mirror is already current**, comparing *layer*
  digests. The push adds an OCI source label, so the mirror's manifest and
  config digests never equal upstream's even when content is identical — a
  manifest comparison would re-copy on every run.
- **Stages to disk rather than `crane copy`.** A streamed copy holds the upload
  open for the whole download, and against a slow source the destination
  cancels it (`stream ID 5; CANCEL; received from peer`).
- Defaults to `linux/amd64`; `crane` defaults to `all`, and mirroring an unused
  architecture doubles the bytes over exactly the leg being avoided.
- Destination must be **ghcr.io** — the push uses the caller's `GITHUB_TOKEN`.
  The pushed package is private and linked to the calling repo; making it
  **public** is simpler for a mirror of an already-public image and removes the
  need for `credentials:` on the consumer's `container:`.
- The consumer must keep its own pin (image tag, and any client library
  version that must match it) in step — this workflow mirrors, it does not
  reconcile. See `cshuttle/nmon` `.github/workflows/lockstep.yml` for one way
  to enforce that.

## Git hooks

### `lefthook/base.yml`

Shared advisory pre-commit hooks (shellcheck, gitleaks, ggshield, yamllint,
whitespace / merge-conflict). Consume from any repo with a tiny `lefthook.yml`:

```yaml
remotes:
  - git_url: https://github.com/cshuttle/workflows
    ref: main
    configs:
      - lefthook/base.yml
```

Then `lefthook install` per clone. Tools expected on PATH: `lefthook`,
`shellcheck`, `gitleaks`, `ggshield`, `yamllint`. `ggshield` also needs a
GitGuardian token (`ggshield auth login` or `GITGUARDIAN_API_KEY`); without one
its hook self-skips (advisory) — `gitleaks` still runs offline.

## Standards

### `STANDARDS.md`

The canonical engineering standards for the estate — change flow, lint/format
(Trunk is normative), commit/PR conventions, secrets rules, ADR practice, docs
conventions, and the per-repo `AGENTS.md` contract. Every repo's root
`AGENTS.md` links here and carries only repo-specific deltas.

### `configs/markdownlint.yaml`

Shared pragmatic markdownlint profile (defaults on; noisy prose/structural
rules off). Copy into a repo as `.trunk/configs/.markdownlint.yaml` and remove
`markdownlint` from `lint.disabled` in `.trunk/trunk.yaml`. Strict adoption is
tracked in #7.
