"""Test helper (no tests here): the program's list of its agents, .aibl/course-agents.json.

Built the way the course's publish step builds it (agent-native-workforce-internal,
scripts/student_branch.py): every aibl-*.md directly in .claude/agents that the branch ever
had, current or retired, with the sha256 of every version it had, as committed (LF) and as
Git for Windows checks it out (CRLF), and the current version's two sha256 for a current one.
"""
import hashlib, json, re, subprocess
from pathlib import Path

LIST = ".aibl/course-agents.json"
AGENT = re.compile(r"aibl-[a-z0-9-]+\.md")


def converted(raw):
    """Whether Git for Windows (core.autocrlf=true) turns LF into CRLF on checkout: git's own text test
    (no NUL, no CR at all, printable >> 7 not below nonprintable), as the publish step applies it."""
    if b"\0" in raw or b"\r" in raw:
        return False
    printable = nonprintable = 0
    for c in raw:
        if c == 127 or (c < 32 and c not in (8, 9, 10, 12, 27)):
            nonprintable += 1
        elif c != 10:
            printable += 1
    return b"\n" in raw and (printable >> 7) >= nonprintable


def forms(raw):
    """As committed, and as Git for Windows checks it out."""
    out = {hashlib.sha256(raw).hexdigest()}
    if converted(raw):
        out.add(hashlib.sha256(raw.replace(b"\n", b"\r\n")).hexdigest())
    return out


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def build(repo):
    """The list for the edition about to be committed in repo: its history plus its working tree."""
    repo = Path(repo)
    published = {}
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "-q", "HEAD"], capture_output=True)
    if head.returncode == 0:
        for commit in _git(repo, "rev-list", "HEAD").decode().split():
            for line in _git(repo, "ls-tree", commit, ".claude/agents/").decode().splitlines():
                meta, _, p = line.partition("\t")
                name = p.rsplit("/", 1)[-1]
                if meta.split()[1] == "blob" and AGENT.fullmatch(name):
                    published.setdefault(name, set()).update(forms(_git(repo, "cat-file", "blob", meta.split()[2])))
    current = {}
    folder = repo / ".claude" / "agents"
    for f in sorted(folder.iterdir()) if folder.is_dir() else []:
        if f.is_file() and AGENT.fullmatch(f.name):
            current[f.name] = forms(f.read_bytes())
            published.setdefault(f.name, set()).update(current[f.name])
    agents = {}
    for name in sorted(published):
        entry = {"status": "current" if name in current else "retired", "published_sha256": sorted(published[name])}
        if name in current:
            entry["current_sha256"] = sorted(current[name])
        agents[name] = entry
    return {"version": 1, "agents": agents}


def write(repo):
    """Write the list into repo's working tree, ready to commit with the edition."""
    path = Path(repo) / LIST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build(repo), indent=2, sort_keys=True) + "\n")


def adopt(workbench, rev="agent-workforce/student"):
    """Put the list from rev (a fetched program edition) into the workbench, as a merge would."""
    path = Path(workbench) / LIST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_git(workbench, "show", f"{rev}:{LIST}"))
