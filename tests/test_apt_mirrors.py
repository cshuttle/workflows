"""Check scripts/apt-mirrors.sh rewrites Ubuntu sources and leaves the rest."""

import os
import subprocess
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "apt-mirrors.sh"

DEB822 = """Types: deb
URIs: http://archive.ubuntu.com/ubuntu/
Suites: noble noble-updates noble-backports
Components: main universe

Types: deb
URIs: http://security.ubuntu.com/ubuntu/
Suites: noble-security
Components: main universe
"""
LEGACY = "deb http://azure.archive.ubuntu.com/ubuntu/ noble main\n"
PPA = "deb https://ppa.launchpadcontent.net/git-core/ppa/ubuntu/ noble main\n"


def run(root, mirrors=None):
    env = dict(os.environ, APT_MIRRORS_ROOT=str(root))
    env.pop("APT_MIRRORS", None)
    if mirrors is not None:
        env["APT_MIRRORS"] = mirrors
    return subprocess.run(
        ["sh", str(SCRIPT)], env=env, check=True, capture_output=True, text=True
    ).stdout


def setup(root):
    d = root / "etc/apt/sources.list.d"
    d.mkdir(parents=True)
    (d / "ubuntu.sources").write_text(DEB822)
    (d / "git-core.list").write_text(PPA)
    (root / "etc/apt/sources.list").write_text(LEGACY)


def main():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        setup(root)
        out = run(root)
        sources = (root / "etc/apt/sources.list.d/ubuntu.sources").read_text()
        assert "ubuntu.com" not in sources, sources
        assert sources.count("URIs: mirror+file:/etc/apt/apt-mirrors.txt") == 2, sources
        assert (root / "etc/apt/sources.list.d/git-core.list").read_text() == PPA
        legacy = (root / "etc/apt/sources.list").read_text()
        assert legacy == "deb mirror+file:/etc/apt/apt-mirrors.txt noble main\n", legacy
        lines = (root / "etc/apt/apt-mirrors.txt").read_text().splitlines()
        assert lines[0] == "https://mirrors.edge.kernel.org/ubuntu/\tpriority:1", lines
        assert lines[2] == "http://archive.ubuntu.com/ubuntu/\tpriority:3", lines
        assert len(lines) == 3, lines
        assert "rewrote /etc/apt/sources.list.d/ubuntu.sources" in out, out
        conf = (root / "etc/apt/apt.conf.d/99apt-mirrors").read_text()
        assert 'Acquire::http::Timeout "15";' in conf, conf

        # A second run changes nothing in the sources and warns.
        out = run(root)
        assert (root / "etc/apt/sources.list.d/ubuntu.sources").read_text() == sources
        assert "::warning::" in out, out

    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        setup(root)
        run(root, mirrors="https://a.example/ubuntu/\n\nhttps://b.example/ubuntu/\n")
        lines = (root / "etc/apt/apt-mirrors.txt").read_text().splitlines()
        assert lines == [
            "https://a.example/ubuntu/\tpriority:1",
            "https://b.example/ubuntu/\tpriority:2",
        ], lines
    print("ok")


if __name__ == "__main__":
    main()
