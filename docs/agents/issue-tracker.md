# Issue tracker

**Estate-wide conventions — tracker, the `gh`/MCP split, and the branch → PR →
squash-merge landing loop — are defined once in the `homelab-memory-model`
skill** ("Per-repo agent config"). Read it there; it is not copied here.
Why: [ADR 0009](https://github.com/cshuttle/Homelab-Skills/blob/main/docs/adr/0009-per-repo-agent-config.md).

Local to this repo:

- **Repo**: `cshuttle/workflows` — reusable GitHub Actions workflows, called by
  the rest of the estate.
- **PRs as a request surface**: no.
- **What merging does**: **it changes CI for every calling repo at once.**
  Callers reference these workflows by ref, so a merge here takes effect on
  their next run with nothing to bump on their side. A broken workflow is an
  estate-wide breakage, not a local one.
- **Runner policy**: jobs run on ARC self-hosted runners (`arc-<repo>`); the
  estate has a **zero-`ubuntu-latest`** policy. `homelab-arc-runners` owns the
  runner side, including the dind prerequisites and the bare-image gotchas.
