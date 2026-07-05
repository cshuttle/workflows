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
