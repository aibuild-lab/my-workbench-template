"""Robot run of aibl-update's Codex waiting path, against stand-in local remotes. Opt-in.

`codex exec` can't click Allow: it runs with approval policy never, so no permission can be asked.
That is exactly the "no box comes" case of the skill's "If it isn't allowed, wait" rule, so this
robot proves the waiting path at each kind of protected write; Wade's hand checks in the Codex app
cover Allow.

Each scenario builds its own workbench from this branch's files, enrolled in a stand-in Agent
Workforce whose `student` branch has a "Week 2" edition, and a stand-in template whose `main` has a
newer aibl-update. The remotes keep their official URLs, as a real workbench's do; the stand-ins are
fetched once beforehand through a one-command insteadOf rewrite (as the other update tests do), so
nothing in the run can reach GitHub and the sandbox's fetch fails like any refused write.
Scenarios start at a given step, with the earlier steps stated in the prompt as done:

  start     the whole update from the start (first write: step 1's network check or step 2's fetch)
  fetch     from step 2, after step 1 (first write: the fetch)
  agents    step 2's checkout of the chosen core paths, which writes .git and .agents
  merge     step 6's merge, after the student's yes
  commit    step 6's commit, the merge already in place (MERGE_HEAD present)
  checkpoint  aibl-checkpoint's save of one changed note (first write: the commit)
  enroll    aibl-enroll's step 6 on a workbench not yet enrolled (first write: the merge)

Pass for each: the workbench is exactly as it was (HEAD, refs, status, merge state); a plain line
ending "Codex will ask ... choose Allow." was said; a waiting line with "try again" was said; no
command was handed to the student; no write was joined to another command; no quote of the skill, file
link or talk of approval policies reached the student. Every command Codex ran
and every message it wrote are saved for reading.

Run: AIBL_CODEX_ROBOT=1 AIBL_CODEX_ROBOT_OUT=<folder> python -m unittest tests.codex_waiting_robot
Optional: AIBL_CODEX_ROBOT_ONLY=merge,commit to run some scenarios. Uses the Codex subscription.
"""
import concurrent.futures, io, json, os, re, shutil, subprocess, tarfile, tempfile, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = {"agent-workforce": "https://github.com/aibuild-lab/agent-workforce.git",
            "template": "https://github.com/aibuild-lab/my-workbench-template.git"}
ORIGIN = "https://github.com/aibl-robot-student/my-workbench.git"  # never reached: no push, network off
GIT_WRITE = re.compile(r"\bgit(\.exe)?\s+(-C\s+\S+\s+)?(remote\s+add|fetch|checkout|merge|commit|add|revert|reset|stash|push|pull)\b")

LEAD = ("I'm a student in Codex. Use the workbench skill aibl-update (read .agents/skills/aibl-update/SKILL.md "
        "completely and follow it exactly, including its section \"In Codex: one permission for each protected write\"). ")
SCENARIOS = {
    "start": LEAD + "Bring Week 2 into my workbench: run the course update, show me what it will change before anything "
             "changes, keep everything I made in Week 1, and ask my yes. Then tell me in one line whether Week 2's "
             "lessons are in, and stop.",
    "fetch": LEAD + "Step 1 is already done in this conversation: you confirmed this is my workbench, its backup on "
             "GitHub is my own private repository, and nothing is unsaved. Go on from step 2 and bring Week 2 in. "
             "Stop at the first point where you need me.",
    "agents": LEAD + "Steps 1 and 2's preview are already done in this conversation: you fetched the template's main "
              "and pinned it at {template_sha}; aibl-update differs; you showed me the diff and I chose \"take "
              "template\" for both copies, .claude/skills/aibl-update and .agents/skills/aibl-update, and \"keep mine\" "
              "for everything else. Don't fetch again. Go on with step 2's apply for exactly those two paths, and stop "
              "at the first point where you need me.",
    "merge": LEAD + "Steps 1 to 5 are already done in this conversation: I kept my core skills, the check found that "
             "Agent Workforce has a new edition (Week 2), agent-workforce/student is fetched and pinned at "
             "{course_sha}, you showed me the preview and there were no clashes, and I said yes. Don't fetch again. "
             "Go on with step 6: bring Week 2 in. Stop at the first point where you need me.",
    "commit": LEAD + "Steps 1 to 5 are done, and in step 6 the merge of agent-workforce/student at {course_sha} is "
              "already in place, not yet saved; you showed me the staged changes and I approved them. Go on with "
              "step 6: save it. Don't merge again and don't cancel. Stop at the first point where you need me.",
    # aibl-checkpoint: a changed note, saved (its first write is the commit).
    "checkpoint": "I'm a student in Codex. Use the workbench skill aibl-checkpoint (read .agents/skills/aibl-checkpoint/SKILL.md "
                  "completely and follow it exactly, including its section \"In Codex: one permission for each protected write\"). "
                  "Save my work: the change to my project note in context/project.md, with the label \"Project note, second "
                  "pass\". You've already shown me what changed and I approve that label and that one file. Stop at the first "
                  "point where you need me.",
    # aibl-enroll: a workbench not yet enrolled, the program fetched and pinned (its first write is the merge).
    "enroll": "I'm a student in Codex. Use the workbench skill aibl-enroll (read .agents/skills/aibl-enroll/SKILL.md "
              "completely and follow it exactly, including its section \"In Codex: one permission for each protected write\"). "
              "Steps 1 to 5 are already done in this conversation for Agent Workforce: this is my workbench with my private "
              "backup, nothing is unsaved, I have access, the agent-workforce remote is connected and its student branch is "
              "fetched and pinned at {course_sha}, the incoming tree checked out, there are no collisions, and I approved the "
              "whole preview. Don't fetch again. Go on with step 6. Stop at the first point where you need me.",
}


def run(cmd, cwd=None, check=True, **kw):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    if check and r.returncode != 0:
        raise RuntimeError(f"{cmd}: {r.stdout}{r.stderr}")
    return r


def git(repo, *args, check=True):
    return run(["git", "-C", str(repo), "-c", "user.name=Robot Student", "-c", "user.email=robot@example.invalid",
                "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args], check=check)


def write(repo, files):
    for name, body in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body.encode())


def extract(rev, dest):
    raw = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", rev], capture_output=True, timeout=120).stdout
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        tar.extractall(dest, filter="data")


def build(base, scenario):
    """Stand-in remotes and one enrolled workbench, ready for the scenario. Returns the workbench and shas."""
    template, course, wb = base / "standin-template", base / "standin-agent-workforce", base / "workbench"
    for repo, branch in ((template, "main"), (course, "student"), (wb, "main")):
        repo.mkdir()
        git(repo, "init", "-q", "-b", branch)
    # The template: this branch's files, then a newer aibl-update (so step 2 has a real choice).
    extract("HEAD", template)
    git(template, "add", "-A")
    git(template, "commit", "-qm", "Template")
    for app in (".claude", ".agents"):
        p = template / app / "skills/aibl-update/SKILL.md"
        p.write_bytes(p.read_bytes() + b"\n<!-- stand-in: a newer copy of this skill -->\n")
    git(template, "commit", "-qam", "Newer aibl-update")
    # The program: Week 1, then Week 2 (new lessons, a new skill, a new Codex agent).
    write(course, {".aibl/programs/agent-workforce.json": json.dumps({"program": "agent-workforce", "edition": "week-1"}) + "\n",
                   "course/workforce/lessons/anw-l01.md": "# Week 1 Lesson 1 (stand-in)\n",
                   ".agents/skills/aibl-workforce/SKILL.md": "---\nname: aibl-workforce\ndescription: stand-in\n---\n",
                   ".codex/agents/aibl-the-professor.toml": "name = \"aibl-the-professor\"\n"})
    git(course, "add", "-A")
    git(course, "commit", "-qm", "Week 1")
    # The workbench: made from the template's first commit, with this branch's aibl-update.
    extract("HEAD", wb)
    git(wb, "add", "-A")
    git(wb, "commit", "-qm", "My workbench")
    git(wb, "config", "user.name", "Robot Student")
    git(wb, "config", "user.email", "robot@example.invalid")
    git(wb, "remote", "add", "origin", ORIGIN)
    for remote, url in OFFICIAL.items():
        git(wb, "remote", "add", remote, url)
    redirect = ["-c", f"url.{course.as_posix()}.insteadOf={OFFICIAL['agent-workforce']}",
                "-c", f"url.{template.as_posix()}.insteadOf={OFFICIAL['template']}"]
    git(wb, *redirect, "fetch", "-q", "agent-workforce", "student")
    if scenario == "enroll":  # not enrolled yet: the program is fetched and pinned, nothing merged
        return wb, {"course_sha": git(wb, "rev-parse", "agent-workforce/student").stdout.strip()}
    git(wb, "merge", "-q", "--allow-unrelated-histories", "--no-ff", "-m", "Add Agent Workforce", "agent-workforce/student")
    write(course, {".aibl/programs/agent-workforce.json": json.dumps({"program": "agent-workforce", "edition": "week-2"}) + "\n",
                   "course/workforce/lessons/anw-w2-keep.md": "# Week 2 Lesson 1 (stand-in)\n",
                   "course/workforce/prompts/anw-w2-keep.txt": "stand-in start box\n",
                   ".agents/skills/aibl-content-desk/SKILL.md": "---\nname: aibl-content-desk\ndescription: stand-in\n---\n",
                   ".codex/agents/aibl-cipher.toml": "name = \"aibl-cipher\"\n"})
    git(course, "add", "-A")
    git(course, "commit", "-qm", "Week 2: keep it or swap it, the content desk, Cipher")
    git(wb, *redirect, "fetch", "-q", "agent-workforce", "student")
    git(wb, *redirect, "fetch", "-q", "template", "main")
    shas = {"course_sha": git(wb, "rev-parse", "agent-workforce/student").stdout.strip(),
            "template_sha": git(wb, "rev-parse", "template/main").stdout.strip()}
    if scenario == "commit":
        git(wb, "merge", "--no-ff", "--no-commit", "agent-workforce/student")
    if scenario == "checkpoint":  # one changed, tracked note, not saved yet
        note = wb / "context/project.md"
        note.write_bytes(note.read_bytes() + b"\nSecond pass: the salon opens at 8 on Saturdays.\n")
    return wb, shas


def state(wb):
    return {"head": git(wb, "rev-parse", "HEAD").stdout.strip(),
            "status": git(wb, "status", "--porcelain", "--untracked-files=all").stdout,
            "refs": git(wb, "for-each-ref", "--format=%(refname) %(objectname)").stdout,
            "merging": (wb / ".git" / "MERGE_HEAD").exists(),
            "config": (wb / ".git" / "config").read_text(encoding="utf-8")}


def items(events):
    """Every item Codex reported, from the JSONL event stream, deduplicated by id (last wins)."""
    seen = {}
    for e in events:
        item = e.get("item") if isinstance(e, dict) else None
        if isinstance(item, dict):
            seen[item.get("id", id(item))] = item
    return list(seen.values())


def walk(name, out):
    base = Path(tempfile.mkdtemp(prefix=f"aibl-robot-{name}-"))
    try:
        wb, shas = build(base, name)
        before = state(wb)
        prompt = SCENARIOS[name].format(**shas)
        last = out / f"{name}-last-message.txt"
        started = time.time()
        r = run([shutil.which("codex"), "exec", "--json", "--ephemeral", "-s", "workspace-write",
                 "-c", "sandbox_workspace_write.network_access=false",
                 "-C", str(wb), "-o", str(last), "-"], check=False, timeout=1500, input=prompt)
        seconds = round(time.time() - started)
        events = []
        for line in r.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        (out / f"{name}-events.jsonl").write_text(r.stdout, encoding="utf-8")
        after = state(wb)
        its = items(events)
        messages = [i.get("text", "") for i in its if i.get("type") == "agent_message"]
        commands = [{"command": i.get("command", ""), "exit_code": i.get("exit_code"), "status": i.get("status"),
                     "output": (i.get("aggregated_output") or "")[-600:]} for i in its if i.get("type") == "command_execution"]
        said = "\n\n".join(messages)
        writes = [c for c in commands if GIT_WRITE.search(c["command"])]
        joined = [c["command"] for c in writes if re.search(r"&&|;\s*git|\|\s*git|git[^\n]*;\s*\S", c["command"].split("-Command", 1)[-1])]
        checks = {
            "workbench unchanged": before == after,
            # aibl-update's Week 2 words, or aibl-checkpoint's and aibl-enroll's Week 1 words
            "plain line said": bool(re.search(r"Codex will ask (you to allow it|to use the network): choose Allow\.|"
                                              r"If Codex asks you to allow [^.]*, that's this (save|step); choose to allow it\.", said)),
            "waiting line said": "try again" in said.lower(),
            "no command handed to the student": not re.search(r"(^|\n)\s*(git|python3?|node|py) ", said) and "```" not in said,
            "no joined write": not joined,
            "no skill quote or file link": "SKILL.md" not in said and "](" not in said and "approval policy" not in said.lower(),
            "codex exited": r.returncode == 0,
        }
        result = {"scenario": name, "seconds": seconds, "exit": r.returncode, "checks": checks,
                  "writes_attempted": writes, "joined": joined, "commands": commands, "messages": messages,
                  "before": before, "after": after, "stderr_tail": r.stderr[-1500:]}
        (out / f"{name}-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        with open(out / f"{name}-transcript.md", "w", encoding="utf-8", newline="\n") as f:
            f.write(f"# Robot: {name}\n\nPrompt:\n\n> {prompt}\n\n{seconds} s, exit {r.returncode}\n\n## Checks\n\n")
            for k, v in checks.items():
                f.write(f"- {'PASS' if v else 'FAIL'}: {k}\n")
            f.write("\n## Commands Codex ran\n\n")
            for c in commands:
                f.write(f"- exit {c['exit_code']}: `{c['command']}`\n")
            f.write("\n## What Codex said\n\n")
            for m in messages:
                f.write(m.strip() + "\n\n---\n\n")
        return result
    finally:
        shutil.rmtree(base, ignore_errors=True)


@unittest.skipUnless(os.environ.get("AIBL_CODEX_ROBOT") == "1" and shutil.which("codex"),
                     "opt-in: set AIBL_CODEX_ROBOT=1 (uses the Codex subscription)")
class CodexWaitingRobot(unittest.TestCase):
    def test_each_protected_write_waits_when_no_permission_can_be_asked(self):
        out = Path(os.environ.get("AIBL_CODEX_ROBOT_OUT") or tempfile.mkdtemp(prefix="aibl-robot-out-"))
        out.mkdir(parents=True, exist_ok=True)
        only = [s for s in os.environ.get("AIBL_CODEX_ROBOT_ONLY", "").split(",") if s] or list(SCENARIOS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(only)) as pool:
            results = list(pool.map(lambda n: walk(n, out), only))
        summary = {r["scenario"]: r["checks"] for r in results}
        (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        for r in results:
            for check, ok in r["checks"].items():
                with self.subTest(scenario=r["scenario"], check=check):
                    self.assertTrue(ok, f"{r['scenario']}: {check} (see {out})")


if __name__ == "__main__":
    unittest.main()
