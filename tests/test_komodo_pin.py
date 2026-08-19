#!/usr/bin/env python3
"""Unit tests for the python embedded in .github/workflows/komodo-pin.yml.

That script edits the line that decides which image version production runs, in
a repo the caller cannot see from its own CI. Nothing downstream re-checks it:
whatever it commits is deployed by the next push hook. So the decisions worth
being sure of — which line it picks, when it refuses, and when it opens a PR
instead of committing — are tested here rather than discovered on a release.

The script talks to the GitHub API through urllib and nothing else, which is
what makes this possible without a fixture server: stub urlopen, run the source,
assert on the requests it made. Stdlib only, like the script itself.

    python3 tests/test_komodo_pin.py
"""
import base64
import io
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

WF = Path(__file__).resolve().parents[1] / ".github/workflows/komodo-pin.yml"

# The step's `run:` is a YAML block scalar holding a heredoc. Take the source
# between the heredoc markers and undo the block's indentation — deliberately
# without a YAML parser, so this test runs on the bare ARC image (no PyYAML).
def embedded_python():
    raw = WF.read_text()
    body = raw.split("<<'PY'\n", 1)[1].rsplit("PY\n", 1)[0]
    indent = min(len(l) - len(l.lstrip()) for l in body.splitlines() if l.strip())
    return "\n".join(l[indent:] if l.strip() else "" for l in body.splitlines())


SRC = embedded_python()

PINS = """# renovate: datasource=docker depName=ghcr.io/cshuttle/nmon
NMON_VERSION=v1.10.0
OTHER_VERSION=v3.1.4
NOT_SEMVER_VERSION=2
"""


class FakeGitHub:
    """Records requests; answers the two GETs the script makes."""

    def __init__(self, pins=PINS):
        self.pins = pins
        self.calls = []

    def __call__(self, req, timeout=None):
        url = req.full_url
        payload = json.loads(req.data) if req.data else None
        self.calls.append((req.method, url.replace("https://api.github.com", ""), payload))
        if req.method == "GET" and "/contents/" in url:
            body = {"content": base64.b64encode(self.pins.encode()).decode(), "sha": "FILESHA"}
        elif req.method == "GET" and "/git/ref/" in url:
            body = {"object": {"sha": "BASESHA"}}
        elif "/pulls" in url:
            body = {"html_url": "https://github.com/o/r/pull/1"}
        else:
            body = {}
        resp = io.BytesIO(json.dumps(body).encode())
        resp.__enter__ = lambda: resp
        resp.__exit__ = lambda *a: None
        return resp


def run(version, key="NMON_VERSION", pins=PINS):
    """Execute the script; -> (exit code or message, GITHUB_OUTPUT text, fake)."""
    fake = FakeGitHub(pins)
    out = Path(tempfile.mkstemp()[1])
    env = {
        "PIN_TOKEN": "t", "PIN_REPO": "o/deploy", "PIN_FILE": "control-plane/pins.toml",
        "PIN_KEY": key, "VERSION": version, "BRANCH": "main", "SRC_REPO": "o/app",
        "GITHUB_OUTPUT": str(out),
    }
    old_env, old_open = dict(os.environ), urllib.request.urlopen
    os.environ.update(env)
    urllib.request.urlopen = fake
    try:
        code = None
        try:
            exec(compile(SRC, "komodo-pin", "exec"), {"__name__": "__main__"})
        except SystemExit as e:
            code = e.code
        return code, out.read_text(), fake
    finally:
        urllib.request.urlopen = old_open
        os.environ.clear()
        os.environ.update(old_env)
        out.unlink()


def writes(fake):
    return [c for c in fake.calls if c[0] == "PUT"]


class KomodoPin(unittest.TestCase):
    def test_minor_bump_commits_to_the_branch(self):
        code, output, fake = run("v1.11.0")
        self.assertEqual(code, None)
        self.assertIn("result=committed", output)
        (method, url, payload), = writes(fake)
        self.assertEqual(payload["branch"], "main")
        self.assertEqual(payload["sha"], "FILESHA")
        self.assertIn("NMON_VERSION v1.10.0 -> v1.11.0", payload["message"])
        # exactly the pinned line moves; every other line survives byte-for-byte
        after = base64.b64decode(payload["content"]).decode()
        self.assertEqual(after, PINS.replace("v1.10.0", "v1.11.0"))

    def test_a_leading_v_is_optional(self):
        _, output, fake = run("1.11.0")
        self.assertIn("result=committed", output)
        self.assertIn("NMON_VERSION=v1.11.0", base64.b64decode(writes(fake)[0][2]["content"]).decode())

    def test_major_opens_a_pull_request_and_commits_nothing_to_main(self):
        code, output, fake = run("v2.0.0")
        self.assertEqual(code, 0)
        self.assertIn("result=pull-request", output)
        (method, url, payload), = writes(fake)
        self.assertEqual(payload["branch"], "pin/nmon-version-v2.0.0")  # not main
        self.assertTrue(any(c[1].endswith("/pulls") for c in fake.calls))

    def test_same_version_is_a_noop(self):
        code, output, fake = run("v1.10.0")
        self.assertEqual(code, 0)
        self.assertIn("result=unchanged", output)
        self.assertEqual(writes(fake), [])

    def test_older_version_is_refused(self):
        # the dispatch button can re-run an old release; that must not roll
        # production back silently
        code, _, fake = run("v1.9.0")
        self.assertIn("older than the pinned", str(code))
        self.assertEqual(writes(fake), [])

    def test_unknown_key_is_refused(self):
        code, _, fake = run("v1.11.0", key="MISSING_VERSION")
        self.assertIn("has 0 lines starting MISSING_VERSION=", str(code))
        self.assertEqual(writes(fake), [])

    def test_ambiguous_key_is_refused(self):
        code, _, fake = run("v1.11.0", pins=PINS + "NMON_VERSION=v1.0.0\n")
        self.assertIn("has 2 lines starting NMON_VERSION=", str(code))
        self.assertEqual(writes(fake), [])

    def test_non_semver_version_is_refused(self):
        code, _, fake = run("latest")
        self.assertIn("not vMAJOR.MINOR.PATCH", str(code))
        self.assertEqual(writes(fake), [])

    def test_non_semver_current_pin_is_refused(self):
        # a pin the script cannot compare is one it must not overwrite by guess
        code, _, fake = run("v1.11.0", key="NOT_SEMVER_VERSION")
        self.assertIn("refusing to overwrite by guess", str(code))
        self.assertEqual(writes(fake), [])

    def test_the_caller_repo_is_recorded_in_the_commit(self):
        _, _, fake = run("v1.11.0")
        self.assertIn("Released by o/app", writes(fake)[0][2]["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
