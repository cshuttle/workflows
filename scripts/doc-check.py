#!/usr/bin/env python3
"""Advisory check for human docs: the mechanical half of STANDARDS.md "Writing rules".

Two checks, both warnings, never a failure:

  avoid   a word the repo's glossary (CONTEXT.md or GLOSSARY.md, run from the
          repo root) lists under `_Avoid_:`. Rule 5, "one word for one thing".
  length  a numbered step over 20 words, or any other sentence over 25. Rule 1.

Review still owns the judgement calls (voice, one instruction per sentence,
whether a term is explained). This only takes the counting off the reviewer:
in Homelab-Skills#1109 four of nine READMEs used an `_Avoid_` word.

Human docs are README.md and docs/**, except docs/agents/. Code fences, inline
code, tables and link targets are skipped: rule 7 keeps code literal.

Old docs follow the rules only after a large edit (STANDARDS.md, Adoption), so
the hook checks only the lines a change adds:

    python3 -I doc-check.py --staged FILE...      # pre-commit: staged lines
    python3 -I doc-check.py --base origin/main FILE...  # review: a branch's lines
    python3 -I doc-check.py FILE...               # every line
"""
import re
import subprocess
import sys
from pathlib import Path

STEP_MAX, SENTENCE_MAX = 20, 25
SKIP_NAMES = {"AGENTS.md", "CLAUDE.md", "CONTEXT.md", "GLOSSARY.md", "CHANGELOG.md"}


def is_human_doc(path):
    p = Path(path)
    if p.suffix != ".md" or p.name in SKIP_NAMES or not p.is_file():
        return False
    parts = p.parts
    if p.name == "README.md":
        return True
    return "docs" in parts and "agents" not in parts[parts.index("docs") + 1:-1]


def glossary(root="."):
    """Return ({avoid phrase: term}, {names that are allowed})."""
    avoids, names = {}, {Path(root).resolve().name.lower()}
    for name in ("CONTEXT.md", "GLOSSARY.md"):
        f = Path(root) / name
        if not f.is_file():
            continue
        term, lines = None, f.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            m = re.match(r"\s*(?:\*\*(.+?)\*\*|#{1,4}\s+(.+?))\s*:?\s*$", line)
            if m:
                term = (m.group(1) or m.group(2)).rstrip(":")
                names.add(term.lower())
                continue
            m = re.match(r"\s*_Avoid_:\s*(.*)", line)
            if not m:
                continue
            text = m.group(1)
            for nxt in lines[i + 1:]:  # an _Avoid_ list may wrap
                if not nxt.strip() or re.match(r"\s*(\*\*|#|_)", nxt):
                    break
                text += " " + nxt.strip()
            text = re.sub(r"\([^)]*\)", "", text)
            for item in re.split(r"[,;]", text):
                item = item.strip().strip(".").strip()
                # A long item is prose ("calling a C4 container a Service"), not a word.
                if item and len(item.split()) <= 3 and re.search(r"[A-Za-z]", item):
                    avoids[item.lower()] = term
    return avoids, names


def prose_blocks(text):
    """Yield (first_line, last_line, is_step, prose) per paragraph, list item or heading."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":  # front matter
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), 0)
        lines = [""] * (end + 1) + lines[end + 1:]
    block, start, last, step, fence = [], 0, 0, False, None
    for n, line in enumerate(lines, 1):
        s = line.strip()
        opener = re.match(r"(`{3,}|~{3,})", s)
        if fence:
            fence = None if opener and s.startswith(fence) else fence
            continue
        item = re.match(r"(\d+[.)]|[-*+])\s+(.*)", s)
        if opener or not s or s.startswith(("|", "<!--", ">", "#")) or item:
            if block:
                yield start, last, step, " ".join(block)
            block = []
            if opener:
                fence = opener.group(1)
            elif s.startswith("#"):
                yield n, n, False, s.lstrip("#").strip()
            elif item:
                block, start, last, step = [item.group(2)], n, n, item.group(1)[0].isdigit()
            continue
        if not block:
            start, step = n, False
        block.append(s)
        last = n
    if block:
        yield start, last, step, " ".join(block)


def clean(prose):
    prose = re.sub(r"`[^`]*`", " CODE ", prose)
    prose = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", prose)
    prose = re.sub(r"<[^>]+>", " ", prose)
    return re.sub(r"[*_]{1,3}", "", prose)


def added_lines(path, git_args):
    """Line numbers the diff adds to path; None means check every line."""
    if git_args is None:
        return None
    out = subprocess.run(["git", "diff", "-U0", *git_args, "--", path],
                         capture_output=True, text=True, check=False).stdout
    lines = set()
    for m in re.finditer(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", out, re.M):
        first, count = int(m.group(1)), int(m.group(2) or 1)
        lines.update(range(first, first + count))
    return lines


def check(path, avoids, names=(), added=None):
    warnings = []
    for line_no, last, is_step, prose in prose_blocks(Path(path).read_text(encoding="utf-8")):
        if added is not None and not added.intersection(range(line_no, last + 1)):
            continue
        text = clean(prose)
        # A glossary term or the repo's own name ("Detected device", "Topology")
        # can contain an avoided word; mask the allowed names first.
        low = text.lower()
        for name in sorted(names, key=len, reverse=True):
            low = re.sub(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", " ", low)
        for phrase in sorted(avoids, key=len, reverse=True):  # "smart device" before "device"
            low, hits = re.subn(r"(?<![\w-])" + re.escape(phrase) + r"(?![\w-])", " ", low)
            if hits:
                warnings.append(f'{path}:{line_no}: avoid "{phrase}": the glossary term is "{avoids[phrase]}"')
        limit = STEP_MAX if is_step else SENTENCE_MAX
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text):
            words = len(sentence.split())
            if words > limit:
                kind = "step" if is_step else "sentence"
                warnings.append(f"{path}:{line_no}: {kind} has {words} words (max {limit}): {sentence[:60]}...")
    return warnings


def main(argv):
    git_args = None
    if argv[:1] == ["--staged"]:
        git_args, argv = ["--cached"], argv[1:]
    elif argv[:1] == ["--base"]:
        git_args, argv = [argv[1]], argv[2:]
    avoids, names = glossary()
    warnings = [w for f in argv if is_human_doc(f)
                for w in check(f, avoids, names, added_lines(f, git_args))]
    for w in warnings:
        print(w)
    if warnings:
        print(f"doc-check: {len(warnings)} warning(s), advisory (STANDARDS.md, Writing rules)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
