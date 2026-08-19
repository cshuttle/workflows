# workflows

Shared **CI definitions** for the `cshuttle` homelab estate: reusable GitHub
Actions workflows (`.github/workflows/`) and the shared **Lefthook** git-hook
config (`lefthook/`).

This repo is intentionally **public** so the private GitOps repos can consume it
— cross-repo reusable workflows between *private* repos require a paid GitHub
plan, but a public host is callable by any repo on any plan, and Lefthook
`remotes:` likewise pull from here. Only generic CI recipes live here; no
secrets, manifests, or hostnames.

## Versioning — read this before cutting a release

Consumers pin an **exact release tag** (`@v1.0.0`), never `@main` and never a
floating major. What this repo publishes is consumed by ~30 repos, so a commit
to the default branch used to change the whole estate's CI the moment it merged
— no pull request anywhere, no record of which repo ran which version. That is
the same reason every third-party action here is pinned by SHA.

Three rules follow from that:

1. **Released tags are immutable and are never moved.** A broken workflow is
   superseded by a new patch release. Moving a tag would silently change every
   consumer that already pinned it — the exact failure the pins remove.
2. **There is no floating `v1`.** Convenient, and the GitHub-ecosystem norm, but
   it re-creates the silent-change problem one level up.
3. **A major bump means consumers must edit their `uses:` line** — an input
   removed or renamed, or behaviour a caller has to react to. Minor is a new
   capability, patch is everything else.

Bumping consumers after a release, by surface:

| Surface | Who moves it |
| --- | --- |
| `.github/workflows/ggshield.yml` (~30 repos) | `REUSABLE_REF` in `Monitoring/scripts/reconcile-ggshield-gate.sh`, then a `--sync-workflow` sweep — one PR per repo. Renovate is deliberately disabled on this generated file so the two cannot rubber-band. |
| The hand-written callers (kustomize-validate, mirror-image, komodo-deploy, komodo-pin) | Renovate |
| Lefthook `remotes:` refs | By hand — Renovate has no manager for them |

The usage examples below pin `v1.0.0`; check the
[releases](https://github.com/cshuttle/workflows/releases) for the current tag.

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
    uses: cshuttle/workflows/.github/workflows/kustomize-validate.yml@v1.0.0
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
    uses: cshuttle/workflows/.github/workflows/ggshield-scan.yml@v1.0.0
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
  uses: cshuttle/workflows/.github/workflows/komodo-deploy.yml@v1.0.0
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

### `komodo-pin.yml`

Moves a deploy **pin** — for stacks that run a *released, pinned* image rather
than a floating tag. `komodo-deploy.yml` above is the wrong tool for those: a
redeploy that does not change the pin re-runs the same image, so the release
never reaches the screen. Called from the release workflow, this writes the
version into the deploy repo's pin file and stops; whatever that repo already
does on a push is what deploys.

```yaml
# final job in the repo's release workflow
pin:
  needs: release
  uses: cshuttle/workflows/.github/workflows/komodo-pin.yml@v1.2.0
  with:
    pin-repo: <owner>/<deploy repo>
    pin-file: path/to/pins.toml
    pin-key: MYAPP_VERSION
    version: ${{ inputs.version }}
    runner: arc-<repo>
  secrets:
    PIN_REPO_TOKEN: ${{ secrets.KOMODO_PIN_TOKEN }}
```

Requires a token with **Contents read/write** (plus **Pull requests write**, for
the major path) on the *deploy repo only*, granted to the caller repo as an
Actions secret — a repo's own `GITHUB_TOKEN` cannot reach another repo.
`pin-repo`/`pin-file` are required by design; this repo names no estate repo or
path.

This is not a dependency bot and does not replace one: Renovate still owns "is
there a newer version, and may it land unattended", and after this runs it
simply finds the pin already current. What it removes is the wait — Renovate's
schedule plus the ghcr tag list, which lags the packages API by minutes
(measured at 3 and 8 on two consecutive releases). A **major** version is not
committed: it opens a PR instead, because a major means the deploy needs a human
step — the same reason `release-image.yml` makes the version a human decision.
The script refuses anything it cannot verify: a non-semver version or current
pin, a key matching zero or several lines, or a version older than the one
pinned (a re-run of an old release must not roll production back).

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
    uses: cshuttle/workflows/.github/workflows/mirror-image.yml@v1.0.0
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
  reconcile. See the `lockstep` job in `playwright-test.yml` (below) for one
  way to enforce that.

### `playwright-test.yml`

The estate's browser testing convention (Homelab-Skills ADR 0017): one
Playwright pin for the whole estate lives in this workflow's
`playwright-image` default, and consumers run their suites inside that
container on their own ARC runner. Extracted from `cshuttle/nmon`
(nmon#76/#78/#79/#125), which proved the pattern: the pinned ghcr mirror
avoids Microsoft's badly-peered registry, and a `lockstep` job holds every PR
red until the caller's `@playwright/test` pin, this workflow's image tag, and
the mirror's actual content agree — each of those drifts silently and late on
its own.

```yaml
# .github/workflows/test.yml in the consuming repo
name: test
on:
  pull_request:
  schedule:
    - cron: "23 5 * * 1" # weekly: catches the mirror being pruned or MCR re-tagging
permissions:
  contents: read
jobs:
  test:
    uses: cshuttle/workflows/.github/workflows/playwright-test.yml@v1.7.0
    with:
      runner: arc-<repo>
      unit-command: npm run test:unit # optional; omit if e2e is the only suite
```

This section is the CI half only. What the repo looks like on the **inside** —
the Playwright config baseline, how the app-under-test boots, test layout, and
the starter smoke — is [docs/playwright-consumer.md](docs/playwright-consumer.md),
the consumer half of the convention. Adopting it in a repo means, one time:

- **An ARC runner with dind.** The test job is a `container:` job; the repo's
  scale set needs `containerMode: dind` and an ephemeral-storage request (see
  `arc-nmon` in `cshuttle/main`, `arc-runners-appset.yaml`).
- **Pin `@playwright/test` exactly** in `devDependencies`, to the version the
  image tag carries (`v1.62.1-noble` → `1.62.1`). Ranges fail lockstep: a
  range lets npm drift ahead of the image and reintroduces a browser download
  from a CDN this site cannot reliably reach.
- **Disable Renovate's playwright npm bumps** in the repo's `renovate.json` —
  the image leads and npm follows (npm publishes ahead of the image; an
  automatic npm bump breaks CI, nmon#76). When Renovate bumps this repo's
  image pin and the consumer's `uses:` tag, update `package.json` in that same
  PR; lockstep holds it red until they agree.

  ```json
  {
    "description": "The estate Playwright pin leads and npm follows (cshuttle/workflows playwright-test.yml; ADR 0017). Bump @playwright/test by hand in the same PR as the uses: tag bump — lockstep holds it red until they agree.",
    "matchPackageNames": ["@playwright/test", "playwright", "playwright-core"],
    "enabled": false
  }
  ```

On failure the caller gets a `playwright-report` artifact (report + traces,
7 days). Bumping the estate pin: Renovate proposes the image bump here once
MCR really has the tag; mirror it (`mirror-playwright.yml`, or crane by hand —
see that workflow's header), merge, cut a release, and Renovate walks the
consumers' `uses:` tags forward.

### `release-image.yml`

Cuts a release for a repo whose artifact is one or more container images. It
does **not** build: the image was built and tested when the commit merged, so
this promotes that existing digest to a version tag, creates an annotated git
tag, and publishes a GitHub Release.

```yaml
# .github/workflows/release.yml in the app repo
name: release
on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version to release, e.g. v1.2.0"
        required: true
      summary:
        description: "Optional paragraph shown above the generated notes"
        required: false
jobs:
  release:
    uses: cshuttle/workflows/.github/workflows/release-image.yml@v1.1.0
    permissions:
      contents: write # push the tag, create the release
      packages: write # add the version tag to the ghcr package
    with:
      version: ${{ inputs.version }}
      summary: ${{ inputs.summary }}
      images: ghcr.io/cshuttle/topology
      runner: arc-<repo>
    secrets:
      # Only for a package GITHUB_TOKEN cannot read — see below. Omit otherwise.
      ghcr-token: ${{ secrets.GHCR_WRITE_TOKEN }}
```

- **Promotes, never rebuilds.** A rebuild on the tag produces a second digest
  from the same source — a different artifact from the one CI tested, for twice
  the build minutes. `images` takes several images that version together (an
  app and its sidecar are one release, not two).
- **Refuses to release a mismatched build.** Unless `verify-source-commit` is
  false, each image's digest must be reachable under a commit-sha tag somewhere
  in the running ref's recent history, so a build still in flight — or one that
  failed after the merge, or came from another branch — cannot be released by
  accident. Repos tag per-commit differently, so `<sha>`, the 7-char short sha
  and `sha-<short>` are all tried.
- **The tag lands on the ref, and provenance is recorded rather than implied.**
  Tagging each image's own build commit reads better, but a `GITHUB_TOKEN`
  cannot create a ref pointing at a commit whose `.github/workflows` differ from
  the default branch's — the API refuses it exactly as a push does. Any CI change
  after the last build triggers that, which is when you are most likely to be
  releasing. Rather than require a PAT with the `workflow` scope in every repo,
  the tag marks the release point and the **tag message and release body name
  the build commit of every image**.
- **Refuses to reuse a tag**, checked against the remote rather than the local
  clone. Released tags are immutable; supersede with a patch instead.
- **A dispatch button, because the version is a human decision** — a major means
  the deploy needs a human step, which no commit message reliably encodes.
- `tag-prefix` applies to the **git** tag only (`chrome-exporter/v1.0.0`), never
  the image tag: `/` is not legal in a docker tag.
- Notes are always GitHub-generated; `summary` is pre-pended when supplied, and
  the promoted digests are listed under it.
- **`require-same-commit: false` for independently-built components.** By default
  every image must resolve to one build commit, which catches a half-updated
  pair shipping under one version. That is wrong for a repo whose images come
  from separate path-filtered workflows — those change independently and almost
  never share a commit, so the release legitimately means "SPA built at X plus
  config built at Y". Each image is still verified against the branch's history;
  the tag lands on the newest resolved commit.
- **`ghcr-token` when the package is user-owned.** On a personal account a
  package bootstrapped by a manual push is owned by the user, not the repo, and
  `GITHUB_TOKEN` gets 403 on it — including on reads, which the registry reports
  as a plain "not found". A repo that pushes with a classic PAT must pass the
  same PAT here. The alternative is granting the repo access under the package's
  *Manage Actions access* settings, after which the secret can be dropped.

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
