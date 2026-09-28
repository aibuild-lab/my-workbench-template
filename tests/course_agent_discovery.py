"""The course's agents come from the program's own list of them, never from a roster kept here.

The 09-27 pre-publish run (finding F1): the next Agent Workforce edition ships 17 agents, but
the agent menu copied only the 8 names on a list kept inside update-check.mjs, so the 9 new
ones came back `skipped` and never reached the @ menu. Tyler's rule (09-24): the team is
discovery-based, never a hardcoded roster. The program's publish step now writes
.aibl/course-agents.json into every edition: each agent, current or retired, with the sha256
of every version the published branch ever had of it. The hook reads that one file from the
workbench's HEAD. A file is the course's only when its bytes are one of those versions.

Synthetic: a throwaway course, workbench and home folder (HOME / USERPROFILE), so the real
~/.claude is never touched. No app, account or installation claim.
"""
import json, os, re, stat, subprocess, sys, tempfile, time, unittest, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import course_list  # noqa: E402  (the program's list of its agents, built as the course builds it)

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "update-check.mjs"
OFFICIAL = "https://github.com/aibuild-lab/agent-workforce.git"
WINDOWS = os.name == "nt"

# the published 09-25 edition (521234a): exactly the eight names the old list held
OLD_EDITION = ["aibl-charter-steward.md", "aibl-chief-of-staff.md", "aibl-echo.md", "aibl-gigawatt.md",
               "aibl-kansa.md", "aibl-librarian.md", "aibl-the-professor.md", "aibl-ygm.md"]
# what the next edition adds (#101, #104): on no list anywhere in the template
NEW_AGENTS = ["aibl-archie.md", "aibl-cinnamon.md", "aibl-cipher.md", "aibl-evidence-pattern-analyst.md",
              "aibl-evy.md", "aibl-hatch.md", "aibl-holler.md", "aibl-sales-discovery.md", "aibl-scratch.md"]
NEW_EDITION = sorted(OLD_EDITION + NEW_AGENTS)
# the course also ships files in .claude/agents that are not agents the menu lists
NOT_AGENTS = {"helper.md": b"a course file, not aibl-\n", "drafts/aibl-draft.md": b"in a subfolder\n"}


def body(name, edition):
    return f"---\nname: {name[:-3]}\n---\n{name} as of {edition}\n".encode()


def crlf(data):
    return data.replace(b"\n", b"\r\n")


def with_preview(run, args):
    """An apply as aibl-update does it: the preview first, then the apply bound to that preview's hash.
    An apply that names its own --expect, or asks for no preview (raw), is passed through as given."""
    args = list(args)
    if args and args[0] == "--agent-menu-apply" and "--expect" not in args and "--raw" not in args:
        args += ["--expect", json.loads(run("--agent-menu"))["preview_sha256"]]
    return [a for a in args if a != "--raw"]


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.menu = self.home / ".claude" / "agents"
        # The course's published student branch: the old 8-agent edition, then the new one
        # (all 17, cipher at v1), then a fix to cipher and the Chief. `old-student` stays on
        # the old edition. Every edition carries the program's stamp and its list of agents.
        self.course = self.base / "course"
        cagents = self.course / ".claude" / "agents"
        for name in OLD_EDITION:
            self.write(cagents / name, body(name, "old"))
        self.write(self.course / ".aibl" / "programs" / "agent-workforce.json", b"{}\n")
        self.git(self.course, "init", "-q", "-b", "student")
        self.commit(self.course, "Student edition, old (8 agents)")
        self.git(self.course, "branch", "old-student")
        for name in NEW_AGENTS:
            self.write(cagents / name, body(name, "new"))
        for rel, data in NOT_AGENTS.items():
            self.write(cagents / rel, data)
        self.commit(self.course, "Student edition, new (17 agents)")
        self.write(cagents / "aibl-cipher.md", body("aibl-cipher.md", "fix"))
        self.write(cagents / "aibl-chief-of-staff.md", body("aibl-chief-of-staff.md", "fix"))
        self.commit(self.course, "Student edition, fix")
        # the hook's own fetch must not reach the network in a test: https is switched off
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), GIT_CONFIG_COUNT="1",
                        GIT_CONFIG_KEY_0="protocol.https.allow", GIT_CONFIG_VALUE_0="never",
                        GIT_TERMINAL_PROMPT="0")

    def tearDown(self):
        for p in self.base.rglob("*"):  # a test may leave a folder read-only
            if p.is_dir() and not p.is_symlink():
                os.chmod(p, stat.S_IRWXU)
        self.temp.cleanup()

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=false", *args], check=True,
                              capture_output=True).stdout

    def commit(self, repo, message):
        if repo == self.course:
            course_list.write(repo)  # every edition carries its list, as the publish step writes it
        self.git(repo, "add", "-A")
        self.git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", message)

    def fetch(self, wb, branch="student"):
        # the remote's effective URL stays official (what the hook verifies); this one fetch
        # reads the local fixture instead
        self.git(wb, "-c", f"url.{self.course}.insteadOf={OFFICIAL}", "fetch", "-q", "agent-workforce",
                 f"+{branch}:refs/remotes/agent-workforce/student")

    def workbench(self, edition, ref="student", with_list=True):
        """A student's workbench on the course's `old` or `fix` edition (its files and its list, as a
        merge brings them), plus the student's own agents. The program branch is fetched at ref."""
        wb = self.base / f"workbench-{edition}-{ref}-{with_list}"
        agents = wb / ".claude" / "agents"
        self.write(wb / ".aibl" / "template.json", b"{}\n")
        if edition == "old":
            for name in OLD_EDITION:
                self.write(agents / name, body(name, "old"))
        else:
            for name in NEW_EDITION:
                self.write(agents / name, body(name, "fix" if name in ("aibl-cipher.md", "aibl-chief-of-staff.md") else
                                                "new" if name in NEW_AGENTS else "old"))
            for rel, data in NOT_AGENTS.items():
                self.write(agents / rel, data)
        if with_list:
            self.write(wb / course_list.LIST, self.git(self.course, "show",
                                                       ("old-student" if edition == "old" else "student") + ":" + course_list.LIST))
        self.write(agents / "aibl-my-own.md", b"an aibl- agent the student made\n")
        self.write(agents / "my-helper.md", b"the student's own, not aibl-\n")
        self.git(wb, "init", "-q", "-b", "main")
        self.commit(wb, "workbench")
        if ref:
            self.git(wb, "remote", "add", "agent-workforce", OFFICIAL)
            self.fetch(wb, ref)
        return wb

    def run_hook(self, wb, *args, stdin=""):
        args = with_preview(lambda *a: self.run_hook(wb, *a), args)
        env = dict(self.env, CLAUDE_PROJECT_DIR=str(wb))
        p = subprocess.run(["node", str(HOOK), *args], input=stdin, text=True, capture_output=True, env=env, cwd=str(wb))
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def report(self, wb):
        return json.loads(self.run_hook(wb, "--agent-menu"))

    def apply(self, wb, *extra):
        return json.loads(self.run_hook(wb, "--agent-menu-apply", *extra))

    def hook_line(self, wb):
        payload = json.dumps({"source": "startup", "session_id": str(uuid.uuid4()), "cwd": str(wb)})
        out = self.run_hook(wb, stdin=payload)
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out.strip() else ""

    def menu_names(self):
        return sorted(p.name for p in self.menu.iterdir()) if self.menu.exists() else []

    def placed(self):
        f = self.home / ".claude" / "aibl-agent-menu-placed.json"
        return json.loads(f.read_text()) if f.exists() else {"agents": {}}


class TheProgramsList(Fixture):
    def test_the_list_holds_current_and_retired_agents_with_every_version(self):
        # what the course's publish step writes (tests/course_list.py builds it the same way)
        self.write(self.course / ".claude" / "agents" / "aibl-scratch.md", b"")
        (self.course / ".claude" / "agents" / "aibl-scratch.md").unlink()
        self.commit(self.course, "Student edition, retires scratch")
        listed = json.loads(self.git(self.course, "show", "student:" + course_list.LIST))
        self.assertEqual(listed["version"], 1)
        self.assertEqual(sorted(listed["agents"]), NEW_EDITION)
        self.assertEqual(listed["agents"]["aibl-scratch.md"]["status"], "retired")
        self.assertEqual(listed["agents"]["aibl-hatch.md"]["status"], "current")
        cipher = listed["agents"]["aibl-cipher.md"]
        self.assertEqual(len(cipher["published_sha256"]), 4)  # two versions, each as LF and as CRLF
        self.assertNotIn("helper.md", listed["agents"])
        self.assertNotIn("aibl-draft.md", listed["agents"])

    def test_a_new_edition_offers_and_applies_every_listed_agent(self):
        wb = self.workbench("fix")
        report = self.report(wb)
        self.assertEqual((report["status"], report["course_agents_from"]), ("out_of_step", "program"))
        self.assertEqual(report["missing"], NEW_EDITION)
        self.assertEqual(report["skipped"], ["aibl-my-own.md"])
        line = self.hook_line(wb)
        for name in NEW_AGENTS:
            self.assertIn(name, line)
        applied = self.apply(wb, "--expect", report["preview_sha256"])
        self.assertEqual(applied["applied"]["errors"], [])
        self.assertEqual(applied["applied"]["copied"], NEW_EDITION)
        self.assertEqual(applied["status"], "in_step")
        self.assertEqual(self.menu_names(), NEW_EDITION)  # and no temp file left behind
        for name in NEW_EDITION:
            self.assertEqual((self.menu / name).read_bytes(), (wb / ".claude" / "agents" / name).read_bytes())
        self.assertNotIn("agent menu", self.hook_line(wb))

    def test_an_old_edition_is_unchanged_whichever_edition_was_fetched(self):
        # the student has not taken the new edition: the result is the old list's, exactly,
        # whether the fetched branch is still the old edition or already the new one
        for ref in ("old-student", "student"):
            with self.subTest(fetched=ref):
                if self.menu.exists():
                    for p in self.menu.iterdir():
                        p.unlink()
                wb = self.workbench("old", ref)
                report = self.report(wb)
                self.assertEqual((report["status"], report["missing"], report["skipped"]),
                                 ("out_of_step", OLD_EDITION, ["aibl-my-own.md"]))
                self.assertEqual((report["changed"], report["edited"], report["leftover"], report["not_ours"],
                                  report["name_conflict"]), ([], [], [], [], []))
                applied = self.apply(wb)
                self.assertEqual((applied["applied"]["errors"], applied["applied"]["copied"]), ([], OLD_EDITION))
                self.assertEqual(applied["status"], "in_step")
                self.assertEqual(self.menu_names(), OLD_EDITION)
                self.assertNotIn("agent menu", self.hook_line(wb))

    def test_a_fresh_or_shallow_clone_offline_needs_nothing_but_its_head(self):
        # enrolled the way aibl-enroll does it, pushed, then cloned fresh on a new computer:
        # only `origin`, no program ref, and https off, so any fetch fails as it would offline
        wb = self.base / "enrolled"
        self.write(wb / ".aibl" / "template.json", b"{}\n")
        self.write(wb / ".claude" / "agents" / "aibl-my-own.md", b"an aibl- agent the student made\n")
        self.git(wb, "init", "-q", "-b", "main")
        self.commit(wb, "workbench")
        self.git(wb, "remote", "add", "agent-workforce", OFFICIAL)
        self.fetch(wb)
        self.git(wb, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "merge", "-q",
                 "--allow-unrelated-histories", "--no-ff", "-m", "Add Agent Workforce", "agent-workforce/student")
        origin = self.base / "origin.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(wb), str(origin)], check=True, capture_output=True)
        for depth in (None, "1"):
            with self.subTest(depth=depth):
                if self.menu.exists():
                    for p in self.menu.iterdir():
                        p.unlink()
                fresh = self.base / f"fresh-{depth}"
                extra = ["--depth", depth] if depth else []
                subprocess.run(["git", "clone", "-q", *extra, origin.as_uri(), str(fresh)], check=True, capture_output=True)
                self.git(fresh, "remote", "add", "agent-workforce", OFFICIAL)  # re-added, never fetched
                report = self.report(fresh)
                self.assertEqual((report["status"], report["missing"]), ("out_of_step", NEW_EDITION))
                self.assertIn("aibl-hatch.md", self.hook_line(fresh))  # its fetch fails; it still speaks
                applied = self.apply(fresh)
                self.assertEqual((applied["applied"]["errors"], applied["applied"]["copied"]), ([], NEW_EDITION))

    def test_a_list_that_does_not_read_names_no_agents(self):
        wb = self.workbench("fix", ref=None)
        (wb / course_list.LIST).write_text('{"version": 1, "agents": {"aibl-hatch.md": {"status": "sometimes"}}}\n')
        self.commit(wb, "a broken list")
        report = self.report(wb)
        self.assertEqual((report["status"], report["course_agents_from"], report["missing"]), ("no_agents", "unreadable", []))
        self.apply(wb)
        self.assertEqual(self.menu_names(), [])

    def test_the_timing_does_not_depend_on_the_history(self):
        # one file read from HEAD: a workbench with 5,000 commits takes no longer than one with 1
        wb = self.workbench("fix", ref=None)
        start = time.monotonic()
        self.report(wb)
        small = time.monotonic() - start
        stream = []
        for i in range(5000):
            stream.append(f"commit refs/heads/main\ncommitter t <t@example.invalid> {1700000000 + i} +0000\n"
                          f"data 6\nnote {i % 10}\n" + ("from refs/heads/main^0\n" if i == 0 else "") +
                          f"M 100644 inline work/note.txt\ndata {len(str(i)) + 1}\n{i}\n")
        subprocess.run(["git", "-C", str(wb), "fast-import", "--quiet"], input="".join(stream).encode(),
                       check=True, capture_output=True)
        self.git(wb, "reset", "-q", "--hard", "main")
        count = int(self.git(wb, "rev-list", "--count", "HEAD").decode())
        self.assertGreater(count, 5000)
        start = time.monotonic()
        report = self.report(wb)
        big = time.monotonic() - start
        self.assertEqual(report["missing"], NEW_EDITION)
        print(f"\n  --agent-menu: {small:.2f}s at 1 commit, {big:.2f}s at {count} commits", file=sys.stderr)
        self.assertLess(big, max(5.0, small * 3))


class NameConflicts(Fixture):
    def test_a_personal_menu_agent_with_a_newly_shipped_course_name_is_never_replaced(self):
        # an older-edition student made ~/.claude/agents/aibl-hatch.md; the course now ships aibl-hatch
        mine = b"my own hatch, made before the course had one\n"
        self.write(self.menu / "aibl-hatch.md", mine)
        wb = self.workbench("fix")
        report = self.report(wb)
        self.assertEqual((report["edited"], report["changed"]), (["aibl-hatch.md"], []))
        self.assertIn("may be an agent of their own that only shares a course agent's name", self.hook_line(wb))
        applied = self.apply(wb)
        self.assertEqual((self.menu / "aibl-hatch.md").read_bytes(), mine)
        self.assertNotIn("aibl-hatch.md", applied["applied"]["claimed"] + applied["applied"]["copied"])
        self.assertNotIn("aibl-hatch.md", self.placed()["agents"])
        self.apply(wb)
        self.assertEqual((self.menu / "aibl-hatch.md").read_bytes(), mine)

    def test_a_workbench_agent_with_a_course_name_but_not_course_bytes_is_the_students(self):
        mine = b"my own hatch, in my workbench\n"
        wb = self.workbench("fix")
        self.write(wb / ".claude" / "agents" / "aibl-hatch.md", mine)
        self.commit(wb, "my own hatch")
        report = self.report(wb)
        self.assertEqual(report["name_conflict"], ["aibl-hatch.md"])
        self.assertIn("aibl-hatch.md", report["skipped"])
        self.assertNotIn("aibl-hatch.md", report["missing"])
        self.assertIn("name conflicts", self.hook_line(wb))
        applied = self.apply(wb)
        self.assertNotIn("aibl-hatch.md", applied["applied"]["copied"])
        self.assertFalse((self.menu / "aibl-hatch.md").exists())
        self.assertNotIn("aibl-hatch.md", self.placed()["agents"])
        # the student put the same file in the menu themselves: still a conflict, still never
        # claimed, and both copies stay exactly as they are
        self.write(self.menu / "aibl-hatch.md", mine)
        report = self.report(wb)
        self.assertEqual((report["name_conflict"], report["status"]), (["aibl-hatch.md"], "needs_a_decision"))
        self.assertIn("name conflicts", self.hook_line(wb))
        self.apply(wb)
        self.assertNotIn("aibl-hatch.md", self.placed()["agents"])
        self.assertEqual((self.menu / "aibl-hatch.md").read_bytes(), mine)
        self.assertEqual((wb / ".claude" / "agents" / "aibl-hatch.md").read_bytes(), mine)
        # later the workbench takes the course's aibl-hatch: the menu copy is still theirs
        self.write(wb / ".claude" / "agents" / "aibl-hatch.md", body("aibl-hatch.md", "new"))
        self.commit(wb, "took the course's hatch")
        report = self.report(wb)
        self.assertEqual((report["edited"], report["changed"], report["name_conflict"]), (["aibl-hatch.md"], [], []))
        self.apply(wb)
        self.assertEqual((self.menu / "aibl-hatch.md").read_bytes(), mine)

    def test_a_mixed_line_ending_file_no_version_has_is_a_name_conflict(self):
        # a published version with only some of its line endings turned into CRLF: its bytes match
        # neither form the list records, so it is not the course's, never copied or recorded
        wb = self.workbench("fix")
        lf = (wb / ".claude" / "agents" / "aibl-hatch.md").read_bytes()
        mixed = lf.replace(b"\n", b"\r\n", 1)
        self.assertNotEqual(mixed, lf)
        self.assertNotEqual(mixed, crlf(lf))
        self.write(wb / ".claude" / "agents" / "aibl-hatch.md", mixed)
        self.commit(wb, "a mixed-ending hatch")
        report = self.report(wb)
        self.assertEqual(report["name_conflict"], ["aibl-hatch.md"])
        self.assertNotIn("aibl-hatch.md", report["missing"])
        # the same bytes in the menu, beside the workbench's own published hatch: the same text, so
        # in step (line endings alone are no difference), but never recorded as a course copy
        self.write(wb / ".claude" / "agents" / "aibl-hatch.md", lf)
        self.commit(wb, "the published hatch again")
        self.write(self.menu / "aibl-hatch.md", mixed)
        report = self.report(wb)
        self.assertIn("aibl-hatch.md", report["in_step"])
        applied = self.apply(wb)
        self.assertNotIn("aibl-hatch.md", applied["applied"]["claimed"])
        self.assertEqual((self.menu / "aibl-hatch.md").read_bytes(), mixed)
        self.assertNotIn("aibl-hatch.md", self.placed()["agents"])

    def test_the_students_own_agents_are_untouched(self):
        wb = self.workbench("fix")
        mine = {"aibl-my-own.md": b"my own, a different copy\n", "my-agent.md": b"mine\n",
                "aibl-someone-else.md": b"never shipped by the course\n"}
        for name, data in mine.items():
            self.write(self.menu / name, data)
        report = self.report(wb)
        self.assertEqual(report["skipped"], ["aibl-my-own.md"])
        self.assertEqual(report["not_ours"], ["aibl-my-own.md", "aibl-someone-else.md"])
        self.apply(wb)
        for name, data in mine.items():
            self.assertEqual((self.menu / name).read_bytes(), data)
        self.assertEqual(self.menu_names(), sorted(NEW_EDITION + list(mine)))

    def test_a_file_that_is_not_a_listed_aibl_agent_is_never_picked_up(self):
        # the course ships helper.md and drafts/aibl-draft.md in .claude/agents; the student has an
        # aibl-draft.md of their own at the top. None of them is on the list.
        wb = self.workbench("fix")
        self.write(wb / ".claude" / "agents" / "aibl-draft.md", b"the student's own draft seat\n")
        self.commit(wb, "my draft seat")
        report = self.report(wb)
        self.assertEqual((report["skipped"], report["name_conflict"]), (["aibl-draft.md", "aibl-my-own.md"], []))
        self.assertNotIn("helper.md", json.dumps(report))
        self.apply(wb)
        self.assertEqual(self.menu_names(), NEW_EDITION)


class Edits(Fixture):
    def test_a_student_edited_agent_is_never_overwritten(self):
        wb = self.workbench("fix")
        hatch = self.menu / "aibl-hatch.md"
        edits = body("aibl-hatch.md", "new") + b"my own line\n"
        self.write(hatch, edits)
        # the Windows rule (#15), for a new agent: an older course version with CRLF line
        # endings is the course's, offered as an update, not the student's edits
        self.write(self.menu / "aibl-cipher.md", crlf(body("aibl-cipher.md", "new")))
        report = self.report(wb)
        self.assertEqual((report["edited"], report["changed"], report["older"]),
                         (["aibl-hatch.md"], ["aibl-cipher.md"], ["aibl-cipher.md"]))
        applied = self.apply(wb)
        self.assertEqual(hatch.read_bytes(), edits)
        self.assertEqual(applied["applied"]["replaced"], ["aibl-cipher.md"])
        self.assertEqual((self.menu / "aibl-cipher.md").read_bytes(), body("aibl-cipher.md", "fix"))
        backup = Path(applied["applied"]["removed_to"])
        self.assertEqual((backup / "replaced" / "aibl-cipher.md").read_bytes(), crlf(body("aibl-cipher.md", "new")))
        self.assertEqual(applied["status"], "needs_a_decision")
        applied = self.apply(wb, "--replace-edited", "aibl-hatch.md")
        self.assertEqual(hatch.read_bytes(), body("aibl-hatch.md", "new"))
        self.assertEqual((Path(applied["applied"]["removed_to"]) / "replaced" / "aibl-hatch.md").read_bytes(), edits)

    def test_a_retired_agent_is_removed_only_when_this_workbench_placed_it(self):
        # a course update retires two seats; the copy this workbench placed is kept in the backup
        # and removed from the menu, the one the student edited since stays exactly as it is
        wb = self.workbench("fix")
        self.apply(wb)
        for name in ("aibl-scratch.md", "aibl-holler.md"):
            (self.course / ".claude" / "agents" / name).unlink()
            (wb / ".claude" / "agents" / name).unlink()
        self.commit(self.course, "Student edition, retires two seats")
        self.fetch(wb)
        course_list.adopt(wb)
        self.commit(wb, "took the edition that retires two seats")
        self.write(self.menu / "aibl-holler.md", b"the student edited this copy\n")
        report = self.report(wb)
        self.assertEqual((report["leftover"], report["not_ours"]), (["aibl-scratch.md"], ["aibl-holler.md"]))
        applied = self.apply(wb, "--expect", report["preview_sha256"])
        self.assertEqual(applied["applied"]["removed"], ["aibl-scratch.md"])
        self.assertEqual((Path(applied["applied"]["removed_to"]) / "aibl-scratch.md").read_bytes(),
                         body("aibl-scratch.md", "new"))
        self.assertFalse((self.menu / "aibl-scratch.md").exists())
        self.assertEqual((self.menu / "aibl-holler.md").read_bytes(), b"the student edited this copy\n")

    def test_anything_changed_after_the_preview_is_refused(self):
        wb = self.workbench("fix")
        self.write(self.menu / "aibl-cipher.md", body("aibl-cipher.md", "new"))
        report = self.report(wb)
        self.assertEqual(report["changed"], ["aibl-cipher.md"])
        # after the preview the student edits that copy: the yes was for what the preview showed
        self.write(self.menu / "aibl-cipher.md", b"edited after the preview\n")
        applied = self.apply(wb, "--expect", report["preview_sha256"])
        self.assertEqual((applied["refused"], applied["applied"]), ("changed_since_preview", None))
        self.assertEqual((self.menu / "aibl-cipher.md").read_bytes(), b"edited after the preview\n")
        self.assertEqual(self.menu_names(), ["aibl-cipher.md"])

    def test_an_apply_without_the_preview_is_refused(self):
        # a stale or blind apply, even one that names an edited copy to replace, writes nothing
        wb = self.workbench("fix")
        self.write(self.menu / "aibl-hatch.md", b"the student's edits\n")
        for extra in ((), ("--replace-edited", "aibl-hatch.md")):
            with self.subTest(extra=extra):
                applied = self.apply(wb, "--raw", *extra)
                self.assertEqual((applied["refused"], applied["applied"]), ("no_preview", None))
                self.assertEqual(self.menu_names(), ["aibl-hatch.md"])
                self.assertEqual((self.menu / "aibl-hatch.md").read_bytes(), b"the student's edits\n")

    def test_a_stale_expect_is_refused(self):
        # the student said yes to replacing their edited copy as it was; they edit it again first
        wb = self.workbench("fix")
        self.write(self.menu / "aibl-hatch.md", b"the student's edits\n")
        preview = self.report(wb)
        self.write(self.menu / "aibl-hatch.md", b"edited again after the yes\n")
        applied = self.apply(wb, "--expect", preview["preview_sha256"], "--replace-edited", "aibl-hatch.md")
        self.assertEqual((applied["refused"], applied["applied"]), ("changed_since_preview", None))
        self.assertEqual((self.menu / "aibl-hatch.md").read_bytes(), b"edited again after the yes\n")
        self.assertEqual(self.apply(wb, "--expect", "0" * 64)["refused"], "changed_since_preview")

    def test_a_workbench_file_changed_after_the_preview_is_refused_too(self):
        # the preview promised the workbench's current Chief; it is swapped for another published
        # version (an older one) before the yes: the apply writes nothing
        wb = self.workbench("fix")
        report = self.report(wb)
        self.write(wb / ".claude" / "agents" / "aibl-chief-of-staff.md", body("aibl-chief-of-staff.md", "old"))
        applied = self.apply(wb, "--expect", report["preview_sha256"])
        self.assertEqual((applied["refused"], applied["applied"]), ("changed_since_preview", None))
        self.assertEqual(self.menu_names(), [])

    @unittest.skipIf(WINDOWS or (hasattr(os, "geteuid") and os.geteuid() == 0), "needs a folder this user cannot write")
    def test_a_failed_write_leaves_every_entry_as_it_was(self):
        wb = self.workbench("fix")
        older = body("aibl-cipher.md", "new")
        self.write(self.menu / "aibl-cipher.md", older)
        before = {p.name: p.read_bytes() for p in self.menu.iterdir()}
        os.chmod(self.menu, 0o555)  # the temp file cannot be written
        try:
            applied = self.apply(wb)
        finally:
            os.chmod(self.menu, 0o755)
        self.assertTrue(any(e.startswith("aibl-cipher.md:") for e in applied["applied"]["errors"]))
        self.assertEqual(applied["applied"]["replaced"], [])
        self.assertEqual({p.name: p.read_bytes() for p in self.menu.iterdir()}, before)  # intact, no temp left


class TheEditionsBeforeTheList(Fixture):
    def test_the_fallback_is_the_eight_agents_of_the_old_list(self):
        source = HOOK.read_text()
        table = source[source.index("const LEGACY_EDITION = {"):source.index("};", source.index("const LEGACY_EDITION = {"))]
        self.assertEqual(sorted(re.findall(r'"(aibl-[a-z0-9-]+\.md)": \{', table)), OLD_EDITION)

    def test_without_a_list_only_those_editions_published_bytes_count(self):
        # HEAD has no list and no program branch is here: only the eight names, and only in the
        # bytes the published editions had. These synthetic files are none of those.
        wb = self.workbench("fix", ref=None, with_list=False)
        report = self.report(wb)
        self.assertEqual(report["course_agents_from"], "legacy_edition")
        self.assertEqual((report["missing"], report["changed"], report["leftover"]), ([], [], []))
        self.assertEqual(report["name_conflict"], OLD_EDITION)
        self.assertEqual(report["skipped"], sorted(NEW_EDITION + ["aibl-my-own.md"]))
        self.apply(wb)
        self.assertEqual(self.menu_names(), [])

    @unittest.skipUnless(os.environ.get("AIBL_PUBLISHED_521234A"),
                         "set AIBL_PUBLISHED_521234A to a checkout of aibuild-lab/agent-workforce at 521234a")
    def test_the_published_521234a_behaves_as_today(self):
        # A real 09-25 workbench: the published edition's own agent files, no list in HEAD.
        published = Path(os.environ["AIBL_PUBLISHED_521234A"]) / ".claude" / "agents"
        wb = self.base / "real-521234a"
        self.write(wb / ".aibl" / "template.json", b"{}\n")
        for f in sorted(published.iterdir()):
            self.write(wb / ".claude" / "agents" / f.name, f.read_bytes())
        self.git(wb, "init", "-q", "-b", "main")
        self.commit(wb, "a 09-25 workbench")
        for form in ("as published", "as a Windows checkout"):
            with self.subTest(form=form):
                if form != "as published":
                    for f in (wb / ".claude" / "agents").iterdir():
                        f.write_bytes(crlf(f.read_bytes().replace(b"\r\n", b"\n")))
                if self.menu.exists():
                    for p in self.menu.iterdir():
                        p.unlink()
                report = self.report(wb)
                self.assertEqual((report["course_agents_from"], report["missing"], report["skipped"], report["name_conflict"]),
                                 ("legacy_edition", OLD_EDITION, [], []))
                applied = self.apply(wb)
                self.assertEqual((applied["applied"]["copied"], applied["status"]), (OLD_EDITION, "in_step"))


if __name__ == "__main__":
    unittest.main()
