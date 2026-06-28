#!/usr/bin/env bash
#
# Render every kustomization root under the given paths (default ".") with
# `kustomize build --enable-helm` and schema-validate the output with
# kubeconform. Single source of truth: called by BOTH the kustomize-validate
# reusable workflow (CI) and the Lefthook pre-push hook (local).
#
# Advisory-friendly: exits 0 (skip) when there are no kustomizations or the
# tools aren't installed, so it never blocks a push in an environment that
# can't run it. Real build/schema failures exit 1.
set -uo pipefail

paths=("$@")
[ "${#paths[@]}" -eq 0 ] && paths=(".")

mapfile -t kfiles < <(find "${paths[@]}" -name kustomization.yaml 2>/dev/null | sort)
if [ "${#kfiles[@]}" -eq 0 ]; then
  echo "kustomize-validate: no kustomizations under ${paths[*]} — skip"; exit 0
fi
for t in kustomize kubeconform; do
  command -v "$t" >/dev/null 2>&1 || { echo "kustomize-validate: $t not installed — skip (advisory)"; exit 0; }
done

built=0; skipped=0; failed=0; fails=""
for kf in "${kfiles[@]}"; do
  d="${kf%/kustomization.yaml}"
  if out="$(kustomize build --enable-helm "$d" 2>/tmp/kv_err)"; then
    if printf '%s' "$out" | kubeconform -strict -summary -ignore-missing-schemas >/dev/null 2>/tmp/kv_kc; then
      built=$((built + 1))
    else
      failed=$((failed + 1)); fails="${fails}  SCHEMA  ${d}"$'\n'"$(sed 's/^/          /' /tmp/kv_kc)"$'\n'
    fi
  elif compgen -G "${d}"/*.sops.yaml >/dev/null || compgen -G "${d}"/*.age >/dev/null; then
    skipped=$((skipped + 1)); echo "  SKIP (sops)  ${d}"
  else
    failed=$((failed + 1)); fails="${fails}  BUILD   ${d}"$'\n'"$(sed 's/^/          /' /tmp/kv_err)"$'\n'
  fi
done

echo "----------------------------------------"
echo "kustomize-validate: built=${built} skipped=${skipped} failed=${failed}"
if [ "${failed}" -gt 0 ]; then printf '%b' "${fails}"; exit 1; fi
