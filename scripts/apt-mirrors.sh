#!/bin/sh
# Point apt's Ubuntu sources at a mirror list, so a dead mirror falls through
# to the next one instead of failing `apt-get update`.
#
# Uses apt's own mirror transport (apt-transport-mirror(1), apt >= 1.6): a
# `mirror+file:` URI names a list of mirrors, and when a fetch from one fails
# apt "automatically" tries the next "until either the file is retrieved or no
# mirror is left". Lower `priority:` is tried first. There is no speed ranking
# (no yum `fastestmirror` equivalent); the order is fixed.
#
# The canonical archive goes LAST, not first. apt picks a mirror per file, so a
# dead first mirror costs its timeout on every file, and an unresolvable name
# also costs the resolver's own timeout, which Acquire::*::Timeout does not
# cover. Measured with archive.ubuntu.com unresolvable: archive first did not
# finish `apt-get update` in 280 s; an independent mirror first took 2 s.
# Independent mirrors trail the archive by a few hours, which CI does not mind.
#
# Why: when Canonical's DNS went down, `archive.ubuntu.com` stopped resolving
# and every job that ran `apt-get install` failed with "Unable to locate
# package", although independent mirrors were serving the same files.
#
# Rewrites archive.ubuntu.com and security.ubuntu.com, and regional names
# under them (us.archive…, azure.archive…), in sources.list and
# sources.list.d (both one-line `.list` and deb822 `.sources`). Third-party
# repos (PPAs) are left alone. Also lowers apt's connect timeout (below).
# Safe to run twice.
#
# Env:
#   APT_MIRRORS       newline-separated mirror URLs, highest priority first
#                     (default: two independent mirrors, then the canonical archive)
#   APT_MIRRORS_ROOT  filesystem root to edit; tests only (default: /)
set -eu

ROOT="${APT_MIRRORS_ROOT:-}"
LIST_PATH=/etc/apt/apt-mirrors.txt
DEFAULT_MIRRORS='https://mirrors.edge.kernel.org/ubuntu/
https://mirror.math.princeton.edu/pub/ubuntu/
http://archive.ubuntu.com/ubuntu/'
MIRRORS="${APT_MIRRORS:-$DEFAULT_MIRRORS}"

mkdir -p "$ROOT/etc/apt/apt.conf.d"
printf '%s\n' "$MIRRORS" | awk 'NF { printf "%s\tpriority:%d\n", $1, ++n }' >"$ROOT$LIST_PATH"

# apt waits up to 120 s on a mirror that does not answer before it moves on.
# 15 s bounds a mirror that accepts and then stalls; it is per attempt, so a
# slow but working mirror is fine. It does not bound a DNS lookup (see above).
printf 'Acquire::http::Timeout "15";\nAcquire::https::Timeout "15";\n' >"$ROOT/etc/apt/apt.conf.d/99apt-mirrors"

changed=0
for f in "$ROOT/etc/apt/sources.list" "$ROOT"/etc/apt/sources.list.d/*.list "$ROOT"/etc/apt/sources.list.d/*.sources; do
	[ -f "$f" ] || continue
	grep -Eq 'https?://([a-z0-9-]+\.)*(archive|security)\.ubuntu\.com/ubuntu/?' "$f" || continue
	sed -Ei "s#https?://([a-z0-9-]+\.)*(archive|security)\.ubuntu\.com/ubuntu/?#mirror+file:$LIST_PATH#g" "$f"
	echo "apt-mirrors: rewrote ${f#"$ROOT"}"
	changed=$((changed + 1))
done

if [ "$changed" -eq 0 ]; then
	echo "::warning::apt-mirrors: no Ubuntu archive source found to rewrite; apt keeps its own sources"
fi
echo "apt-mirrors: $(grep -c . "$ROOT$LIST_PATH") mirrors in $LIST_PATH"
