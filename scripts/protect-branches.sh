#!/usr/bin/env bash
#
# Apply consistent main-branch protection across the cshuttle/* GitHub org.
#
# Tiers (strictness differs; mechanism is uniform):
#   Tier 1 — cluster-impacting GitOps (cshuttle/main). PR required + required
#            status checks (strict) + linear history + block force-push/deletion
#            + conversation resolution. Self-merge (0 reviews) — solo owner.
#   Tier 2 — service stacks, code, shared config. PR required + block
#            force-push/deletion + conversation resolution; required checks where
#            a context is listed in CHECKS and has actually reported.
#   Tier 3 — static / personal / secret stores. Block force-push + deletion
#            only; no PR ceremony.
#
# Design notes:
#   * Reads each repo's DEFAULT branch (some repos default to `master`, not
#     `main`) — never hardcodes the branch name.
#   * Two-pass safe: a required check is only applied once that context has
#     reported on the default branch. A not-yet-seen context is warned and
#     skipped, so re-running after CI lands finishes the job. Never blocks a
#     branch on a check that can never go green.
#   * `enforce_admins=false` everywhere: the owner keeps a break-glass path.
#   * Idempotent — safe to re-run. `DRY_RUN=1` prints the intended body instead
#     of applying. `ONLY=<repo>` limits to one repo.
#
# Requires: gh (authenticated, admin on the org repos), jq.
set -euo pipefail

ORG=cshuttle
DRY_RUN="${DRY_RUN:-0}"
ONLY="${ONLY:-}"

# --- tier membership -------------------------------------------------------
TIER1=(main)
TIER2=(Komodo Omni Garage Garage-Admin Caddy Monitoring MCP-Gateway Semaphore
       blinkstick-mqtt Terraform renovate-config workflows)
TIER3=(Cars WWW MagicMirror .password-store)

# --- desired required-check contexts (';'-separated; repos absent = none) ---
# Context names themselves contain spaces and slashes (e.g. "kustomize /
# validate"), so contexts are separated by ';', never whitespace. Only contexts
# that have actually reported on the default branch are applied.
declare -A CHECKS=(
  [main]="kustomize / validate"
  [workflows]="lefthook-config;actionlint"  # public repo — required checks are free
)

# Split a repo's CHECKS entry into the global `WANT` array (empty if none).
# Must return 0 even when the repo has no checks, else `set -e` aborts the run.
want_for() {
  WANT=()
  if [ -n "${CHECKS[$1]:-}" ]; then IFS=';' read -ra WANT <<<"${CHECKS[$1]}"; fi
}

# --- helpers ---------------------------------------------------------------

# Echo the default branch for a repo.
default_branch() { gh api "repos/$ORG/$1" --jq '.default_branch'; }

# Print, one per line, the subset of requested contexts ($3..) that have
# reported on $1's branch $2. Warn (stderr) about the rest.
present_checks() {
  local repo="$1" br="$2"; shift 2
  [ "$#" -eq 0 ] && return 0
  local have ctx
  have="$(gh api "repos/$ORG/$repo/commits/$br/check-runs" \
            --jq '[.check_runs[].name] | unique' 2>/dev/null || echo '[]')"
  for ctx in "$@"; do
    if jq -e --arg c "$ctx" 'index($c)' >/dev/null <<<"$have"; then
      printf '%s\n' "$ctx"
    else
      echo "  warn: $repo: check '$ctx' not yet reported on $br — skipping (re-run later)" >&2
    fi
  done
}

# Build a JSON array of {context} objects from contexts on stdin (one per line).
checks_json() { jq -R . | jq -s 'map({context: .})'; }

# PUT a protection body ($2) onto $1's default branch (or print it in dry-run).
apply() {
  local repo="$1" body="$2" br
  br="$(default_branch "$repo")"
  if [ "$DRY_RUN" = 1 ]; then
    echo "── $repo ($br) ──"; jq . <<<"$body"; return 0
  fi
  if jq . <<<"$body" | gh api -X PUT \
       "repos/$ORG/$repo/branches/$br/protection" --input - >/dev/null; then
    echo "  ✓ $repo ($br)"
  else
    echo "  ✗ $repo ($br) — FAILED" >&2
  fi
}

skip() { [ -n "$ONLY" ] && [ "$ONLY" != "$1" ]; }

# --- per-tier bodies -------------------------------------------------------

protect_tier1() {
  local repo="$1" br checks
  br="$(default_branch "$repo")"
  want_for "$repo"
  checks="$(present_checks "$repo" "$br" "${WANT[@]}" | checks_json)"
  apply "$repo" "$(jq -n --argjson checks "$checks" '{
    required_status_checks: { strict: true, checks: $checks },
    enforce_admins: false,
    required_pull_request_reviews: {
      dismiss_stale_reviews: false,
      require_code_owner_reviews: false,
      required_approving_review_count: 0
    },
    restrictions: null,
    required_linear_history: true,
    allow_force_pushes: false,
    allow_deletions: false,
    required_conversation_resolution: true
  }')"
}

protect_tier2() {
  local repo="$1" br checks rsc
  br="$(default_branch "$repo")"
  want_for "$repo"
  checks="$(present_checks "$repo" "$br" "${WANT[@]}" | checks_json)"
  # null required_status_checks when there are no present contexts
  if [ "$(jq 'length' <<<"$checks")" -gt 0 ]; then
    rsc="$(jq -n --argjson c "$checks" '{strict:true, checks:$c}')"
  else rsc=null; fi
  apply "$repo" "$(jq -n --argjson rsc "$rsc" '{
    required_status_checks: $rsc,
    enforce_admins: false,
    required_pull_request_reviews: {
      dismiss_stale_reviews: false,
      require_code_owner_reviews: false,
      required_approving_review_count: 0
    },
    restrictions: null,
    allow_force_pushes: false,
    allow_deletions: false,
    required_conversation_resolution: true
  }')"
}

protect_tier3() {
  apply "$1" "$(jq -n '{
    required_status_checks: null,
    enforce_admins: false,
    required_pull_request_reviews: null,
    restrictions: null,
    allow_force_pushes: false,
    allow_deletions: false
  }')"
}

# --- run -------------------------------------------------------------------
echo "Tier 1 (strict — PR + required checks):"
for r in "${TIER1[@]}"; do skip "$r" && continue; protect_tier1 "$r"; done
echo "Tier 2 (PR + force/deletion block):"
for r in "${TIER2[@]}"; do skip "$r" && continue; protect_tier2 "$r"; done
echo "Tier 3 (force/deletion block only):"
for r in "${TIER3[@]}"; do skip "$r" && continue; protect_tier3 "$r"; done
echo "done."
