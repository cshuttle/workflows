# workflows

Shared **reusable GitHub Actions workflows** for the `cshuttle` homelab estate.

This repo is intentionally **public** so the private GitOps repos can call its
workflows via `uses:` — cross-repo reusable workflows between *private* repos
require a paid GitHub plan, but a public host is callable by any repo on any
plan. Only generic CI recipes live here; no secrets, manifests, or hostnames.

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
