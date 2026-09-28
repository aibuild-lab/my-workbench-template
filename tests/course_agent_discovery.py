"""The course's agents are found, never listed: whatever the verified program branch shipped.

The 09-27 pre-publish run (finding F1): the next Agent Workforce edition ships 17 agents, but
the agent menu copied only the 8 names on a list kept inside update-check.mjs, so the 9 new
ones came back `skipped` and never reached the @ menu. Tyler's rule (09-24): the team is
discovery-based, never a hardcoded roster. The course's agents are the aibl-*.md files
directly in .claude/agents that the verified program branch has shipped at any commit.

Synthetic: a throwaway course, workbench and home folder (HOME / USERPROFILE), so the real
~/.claude is never touched. No app, account or installation claim.
"""
import json, os, subprocess, tempfile, unittest, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "update-check.mjs"
OFFICIAL = "https://github.com/aibuild-lab/agent-workforce.git"

# the published 09-25 edition (521234a): exactly the eight names the old list held
OLD_EDITION = ["aibl-charter-steward.md", "aibl-chief-of-staff.md", "aibl-echo.md", "aibl-gigawatt.md",
               "aibl-kansa.md", "aibl-librarian.md", "aibl-the-professor.md", "aibl-ygm.md"]
# what the next edition adds (#101, #104): on no list anywhere, so only discovery finds them
NEW_AGENTS = ["aibl-archie.md", "aibl-cinnamon.md", "aibl-cipher.md", "aibl-evidence-pattern-analyst.md",
              "aibl-evy.md", "aibl-hatch.md", "aibl-holler.md", "aibl-sales-discovery.md", "aibl-scratch.md"]
NEW_EDITION = sorted(OLD_EDITION + NEW_AGENTS)
# the course also ships files in .claude/agents that are not agents the menu lists
NOT_AGENTS = {"helper.md": b"a course file, not aibl-\n", "drafts/aibl-draft.md": b"in a subfolder\n"}


def body(name, edition):
    return f"---\nname: {name[:-3]}\n---\n{name} as of {edition}\n".encode()


def crlf(data):
    return data.replace(b"\n", b"\r\n")


class CourseAgentDiscovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.menu = self.home / ".claude" / "agents"
        # The course's published student branch: the old 8-agent edition, then the new one
        # (all 17, cipher at v1), then a fix to cipher and the Chief. `old-student` stays on
        # the old edition, standing in for the published branch before the new edition landed.
        self.course = self.base / "course"
        cagents = self.course / ".claude" / "agents"
        for name in OLD_EDITION:
            self.write(cagents / name, body(name, "old"))
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
        self.temp.cleanup()

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def git(self, repo, *args):
        subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=false", *args], check=True, capture_output=True)

    def commit(self, repo, message):
        self.git(repo, "add", "-A")
        self.git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", message)

    def fetch(self, wb, branch="student"):
        # the remote's effective URL stays official (what the hook verifies); this one fetch
        # reads the local fixture instead
        self.git(wb, "-c", f"url.{self.course}.insteadOf={OFFICIAL}", "fetch", "-q", "agent-workforce",
                 f"+{branch}:refs/remotes/agent-workforce/student")

    def workbench(self, edition, ref="student"):
        """A student's workbench on the course's `old` or `fix` edition, plus the student's own agents."""
        wb = self.base / f"workbench-{edition}-{ref}"
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
        self.write(agents / "aibl-my-own.md", b"an aibl- agent the student made\n")
        self.write(agents / "my-helper.md", b"the student's own, not aibl-\n")
        self.git(wb, "init", "-q", "-b", "main")
        self.commit(wb, "workbench")
        self.git(wb, "remote", "add", "agent-workforce", OFFICIAL)
        self.fetch(wb, ref)
        return wb

    def run_hook(self, wb, *args, stdin=""):
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

    def test_a_new_edition_offers_and_applies_every_shipped_agent(self):
        wb = self.workbench("fix")
        report = self.report(wb)
        self.assertEqual(report["status"], "out_of_step")
        self.assertEqual(report["missing"], NEW_EDITION)
        self.assertEqual(report["skipped"], ["aibl-my-own.md"])
        line = self.hook_line(wb)
        for name in NEW_AGENTS:
            self.assertIn(name, line)
        applied = self.apply(wb)
        self.assertEqual(applied["applied"]["errors"], [])
        self.assertEqual(applied["applied"]["copied"], NEW_EDITION)
        self.assertEqual(applied["status"], "in_step")
        self.assertEqual(self.menu_names(), NEW_EDITION)
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
                self.assertEqual((report["changed"], report["edited"], report["leftover"], report["not_ours"]),
                                 ([], [], [], []))
                applied = self.apply(wb)
                self.assertEqual((applied["applied"]["errors"], applied["applied"]["copied"]), ([], OLD_EDITION))
                self.assertEqual(applied["status"], "in_step")
                self.assertEqual(self.menu_names(), OLD_EDITION)
                self.assertNotIn("agent menu", self.hook_line(wb))

    def test_a_student_edited_agent_is_never_overwritten(self):
        wb = self.workbench("fix")
        hatch = self.menu / "aibl-hatch.md"
        edits = body("aibl-hatch.md", "new") + b"my own line\n"
        self.write(hatch, edits)
        # the Windows rule (#15), for an agent on no list: an older course version with CRLF
        # line endings is the course's, offered as an update, not the student's edits
        self.write(self.menu / "aibl-cipher.md", crlf(body("aibl-cipher.md", "new")))
        report = self.report(wb)
        self.assertEqual((report["edited"], report["changed"], report["older"]),
                         (["aibl-hatch.md"], ["aibl-cipher.md"], ["aibl-cipher.md"]))
        applied = self.apply(wb)
        self.assertEqual(hatch.read_bytes(), edits)
        self.assertEqual(applied["applied"]["replaced"], ["aibl-cipher.md"])
        self.assertEqual((self.menu / "aibl-cipher.md").read_bytes(), body("aibl-cipher.md", "fix"))
        self.assertEqual(applied["status"], "needs_a_decision")
        # only the student's own yes for that copy replaces it, and the old one goes to a backup
        applied = self.apply(wb, "--replace-edited", "aibl-hatch.md")
        self.assertEqual(hatch.read_bytes(), body("aibl-hatch.md", "new"))
        self.assertEqual((Path(applied["applied"]["removed_to"]) / "replaced" / "aibl-hatch.md").read_bytes(), edits)

    def test_the_students_own_agents_are_untouched(self):
        wb = self.workbench("fix")
        mine = {"aibl-my-own.md": b"my own, a different copy\n", "my-agent.md": b"mine\n",
                "aibl-someone-else.md": b"never shipped by the course\n"}
        for name, data in mine.items():
            self.write(self.menu / name, data)
        report = self.report(wb)
        self.assertEqual(report["skipped"], ["aibl-my-own.md"])
        self.assertEqual(report["not_ours"], ["aibl-my-own.md", "aibl-someone-else.md"])
        self.assertNotIn("aibl-my-own.md", report["missing"] + report["changed"] + report["edited"])
        self.apply(wb)
        for name, data in mine.items():
            self.assertEqual((self.menu / name).read_bytes(), data)
        self.assertEqual(self.menu_names(), sorted(NEW_EDITION + list(mine)))

    def test_a_file_that_is_not_an_aibl_agent_is_never_picked_up(self):
        # the course ships helper.md and drafts/aibl-draft.md in .claude/agents; the student has
        # an aibl-draft.md of their own at the top. None of them is a course agent.
        wb = self.workbench("fix")
        self.write(wb / ".claude" / "agents" / "aibl-draft.md", b"the student's own draft seat\n")
        self.commit(wb, "my draft seat")
        report = self.report(wb)
        self.assertEqual(report["skipped"], ["aibl-draft.md", "aibl-my-own.md"])
        listed = json.dumps(report)
        self.assertNotIn("helper.md", listed)
        self.assertNotIn("my-helper.md", listed)
        self.apply(wb)
        self.assertEqual(self.menu_names(), NEW_EDITION)
        self.assertFalse((self.menu / "drafts").exists())

    def test_an_agent_a_course_update_removes_moves_only_this_workbenchs_own_copy(self):
        # Behavior kept from before: a retired course agent is moved (never deleted) to a dated
        # backup only when this workbench placed exactly those bytes and no longer has the file;
        # a copy edited since is left where it is.
        wb = self.workbench("fix")
        self.apply(wb)
        for name in ("aibl-scratch.md", "aibl-holler.md"):
            (self.course / ".claude" / "agents" / name).unlink()
            (wb / ".claude" / "agents" / name).unlink()
        self.commit(self.course, "Student edition, retires two seats")
        self.commit(wb, "took the edition that retires two seats")
        self.fetch(wb)
        self.write(self.menu / "aibl-holler.md", b"the student edited this copy\n")
        report = self.report(wb)
        self.assertEqual(report["leftover"], ["aibl-scratch.md"])
        self.assertEqual(report["not_ours"], ["aibl-holler.md"])
        applied = self.apply(wb)
        self.assertEqual(applied["applied"]["removed"], ["aibl-scratch.md"])
        self.assertEqual((Path(applied["applied"]["removed_to"]) / "aibl-scratch.md").read_bytes(),
                         body("aibl-scratch.md", "new"))
        self.assertFalse((self.menu / "aibl-scratch.md").exists())
        self.assertEqual((self.menu / "aibl-holler.md").read_bytes(), b"the student edited this copy\n")

    def test_no_verified_program_means_no_course_agents(self):
        # a remote merely named like the program proves nothing: nothing is the course's to copy
        wb = self.workbench("fix")
        self.git(wb, "remote", "set-url", "agent-workforce", str(self.course))
        report = self.report(wb)
        self.assertEqual((report["status"], report["missing"]), ("no_agents", []))
        self.assertEqual(report["skipped"], sorted(NEW_EDITION + ["aibl-my-own.md"]))
        self.apply(wb)
        self.assertEqual(self.menu_names(), [])
        self.assertEqual(self.hook_line(wb), "")


if __name__ == "__main__":
    unittest.main()
