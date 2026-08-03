# 1. Release and versioning model

Status: accepted (2026-08-03)

## Context

Custom software in this estate had no releases. Every artifact was consumed from
a moving reference: container images from `:latest`, shared CI from `@main`,
compiled binaries committed straight into git. Nothing recorded which version of
anything was running, a change to shared CI altered ~30 repos' behaviour the
moment it merged, and one repo drifted 46 commits past its only tag without
anything noticing.

The estate is single-operator with long gaps between sessions, and every
deployment path is already automated: ArgoCD reconciles at HEAD with an
image-updater, and Komodo stacks auto-pull. Any release model that demands
routine manual work will be abandoned; any model that removes the automation
trades a real benefit for a theoretical one.

## Decision

**One tag shape, three meanings.** Everything is `vMAJOR.MINOR.PATCH`. What the
number claims differs by artifact class: for reusable CI it is a compatibility
contract; for applications and binaries it is a rollback anchor and identifier
with no compatibility claim. A **major** for the app class means *the release
cannot be deployed by the normal automated path alone* — a data migration, a new
env var or secret, a hostname change, a manifest edit. Minor is a capability a
user would notice; patch is everything else.

**Released tags are immutable and never move**, and no floating major tag is
published. A broken release is superseded by a patch. Moving a tag would
silently change every consumer that already pinned it.

**Deployments track released versions, gated at majors.** A semver constraint
below the next major lets minors and patches roll automatically while a major
waits for a human to widen it — the automation enforces the definition of major
rather than contradicting it.

**Build once on merge; a release promotes the digest.** Merges keep producing
`:latest` plus a per-commit tag; a release re-tags that existing digest. The
released artifact is then provably the bytes CI tested.

**A release is a dispatch button** taking a version and an optional summary,
because the major judgement cannot be derived from commit text. Notes are
GitHub-generated with the optional summary above them; there is no changelog
file.

**Rollback is a constraint change, not a value change.** On both planes,
reverting the pinned version alone is undone automatically — the ArgoCD updater
re-resolves the newest matching version, and Renovate re-raises the bump. The
lever is narrowing the constraint (a semver bound, or an `allowedVersions` cap),
which also records *why* an artifact is held.

## Consequences

- Two deployment planes with the same model but different speeds: the ArgoCD
  plane rolls in about a minute, the Komodo plane waits for the daily dependency
  run. Deliberate, and cheaper than a cross-repo write credential.
- A version number now costs a decision at release time. That is the point —
  the alternative is a number that decays into permanent patch bumps.
- The dispatch button has no natural reminder, so unreleased drift is surfaced
  by a periodic estate check rather than by the release mechanism itself.
- A commit-driven release bot was rejected on evidence, not taste: version-
  bumping conventional commits are near-absent in two of the five repos, so it
  would have been silently ineffective for 40% of them while appearing to work.
- Compiled binaries share the version scheme but not the workflow — there is one
  such artifact, and generalising for it now would be speculative.

## Notes

Charted and decided across cshuttle/workflows#25 (map), with the reasoning for
each choice recorded on #26, #28, #30, #32 and #47.
