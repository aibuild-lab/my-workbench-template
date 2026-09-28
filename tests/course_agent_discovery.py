"""The course's agents are found, never listed: whatever the verified program branch shipped.

The 09-27 pre-publish run (finding F1): the next Agent Workforce edition ships 17 agents, but
the agent menu copied only the 8 names on a list kept inside update-check.mjs, so the 9 new
ones came back `skipped` and never reached the @ menu. Tyler's rule (09-24): the team is
discovery-based, never a hardcoded roster. The course's agents are the aibl-*.md files
directly in .claude/agents that the verified program branch has shipped at any commit.

Synthetic: a throwaway course, workbench and home folder (HOME / USERPROFILE), so the real
~/.claude is never touched. No app, account or installation claim.
"""
import hashlib, json, os, subprocess, tempfile, unittest, uuid
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
        # every published edition carries the program's stamp, never the template's
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
        self.temp.cleanup()

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def git(self, repo, *args):
        subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=false", *args], check=True, capture_output=True)

    def commit(self, repo, message):
        if repo == self.course:
            self.write_manifest(repo)
        self.git(repo, "add", "-A")
        self.git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", message)

    def write_manifest(self, repo, repository="aibuild-lab/agent-workforce"):
        # the program's edition manifest, as the real student edition ships it: every file with
        # the sha256 of its bytes
        files = []
        for f in sorted((repo / ".claude" / "agents").rglob("*")):
            if f.is_file():
                rel = f.relative_to(repo).as_posix()
                files.append({"path": rel, "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                              "workbench_path": rel, "status": "populated"})
        self.write(repo / ".aibl" / "workforce-student-edition.json", json.dumps(
            {"schema_version": "aibl.student-edition/v1", "repository": repository, "files": files}, indent=2).encode())

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
        # a remote merely named like the program proves nothing, and this workbench never merged
        # the program: nothing is the course's to copy
        wb = self.workbench("fix")
        self.git(wb, "remote", "set-url", "agent-workforce", str(self.course))
        report = self.report(wb)
        self.assertEqual((report["status"], report["missing"]), ("no_agents", []))
        self.assertEqual(report["skipped"], sorted(NEW_EDITION + ["aibl-my-own.md"]))
        self.apply(wb)
        self.assertEqual(self.menu_names(), [])
        self.assertEqual(self.hook_line(wb), "")


    # --- a fresh clone on a new computer: no program remote-tracking ref, perhaps offline ---

    def enrolled_origin(self, branch):
        """A workbench that enrolled (merged the program as aibl-enroll does), pushed to the
        student's own repository. Returns that repository."""
        wb = self.base / f"enrolled-{branch}"
        self.write(wb / ".aibl" / "template.json", b"{}\n")
        self.write(wb / ".claude" / "agents" / "aibl-my-own.md", b"an aibl- agent the student made\n")
        self.git(wb, "init", "-q", "-b", "main")
        self.commit(wb, "workbench")
        self.git(wb, "remote", "add", "agent-workforce", OFFICIAL)
        self.fetch(wb, branch)
        self.git(wb, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "merge", "-q",
                 "--allow-unrelated-histories", "--no-ff", "-m", "Add Agent Workforce", "agent-workforce/student")
        origin = self.base / f"origin-{branch}.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(wb), str(origin)], check=True, capture_output=True)
        return origin

    def fresh_clone(self, origin, name, readd_remote):
        """Cloned fresh: only `origin`, no program ref. Git's https is switched off in these
        tests, so any fetch of the official remote fails exactly as it would offline."""
        fresh = self.base / name
        subprocess.run(["git", "clone", "-q", str(origin), str(fresh)], check=True, capture_output=True)
        if readd_remote:
            self.git(fresh, "remote", "add", "agent-workforce", OFFICIAL)  # re-added, never fetched
        refs = subprocess.run(["git", "-C", str(fresh), "for-each-ref", "refs/remotes/agent-workforce"],
                              text=True, capture_output=True, check=True).stdout
        self.assertEqual(refs, "")
        return fresh

    def test_a_fresh_clone_offline_still_offers_the_agents_it_merged(self):
        origin = self.enrolled_origin("student")
        for readd in (False, True):
            with self.subTest(program_remote_readded=readd):
                if self.menu.exists():
                    for p in self.menu.iterdir():
                        p.unlink()
                fresh = self.fresh_clone(origin, f"fresh-{readd}", readd)
                report = self.report(fresh)
                self.assertEqual((report["status"], report["missing"]), ("out_of_step", NEW_EDITION))
                self.assertEqual(report["skipped"], ["aibl-my-own.md"])
                # the session-start hook: its fetch fails (offline), yet it exits 0 and speaks
                self.assertIn("aibl-hatch.md", self.hook_line(fresh))
                applied = self.apply(fresh)
                self.assertEqual((applied["applied"]["errors"], applied["applied"]["copied"]), ([], NEW_EDITION))
                self.assertEqual(applied["status"], "in_step")
                self.assertEqual(self.menu_names(), NEW_EDITION)

    def test_a_fresh_clone_of_an_old_edition_offers_its_eight(self):
        fresh = self.fresh_clone(self.enrolled_origin("old-student"), "fresh-old", False)
        report = self.report(fresh)
        self.assertEqual((report["status"], report["missing"], report["skipped"]),
                         ("out_of_step", OLD_EDITION, ["aibl-my-own.md"]))
        applied = self.apply(fresh)
        self.assertEqual(applied["applied"]["copied"], OLD_EDITION)
        self.assertEqual(self.menu_names(), OLD_EDITION)

    def test_a_shallow_fresh_clone_finds_its_course_in_the_edition_manifest(self):
        # a depth-1 clone holds no program commit at all, only the merged tree; the program's own
        # edition manifest in it still names each agent and the sha256 of its bytes
        origin = self.enrolled_origin("student")
        fresh = self.base / "fresh-shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", origin.as_uri(), str(fresh)], check=True, capture_output=True)
        shallow = subprocess.run(["git", "-C", str(fresh), "rev-parse", "--is-shallow-repository"],
                                 text=True, capture_output=True, check=True).stdout.strip()
        self.assertEqual(shallow, "true")
        report = self.report(fresh)
        self.assertEqual((report["status"], report["missing"], report["skipped"]),
                         ("out_of_step", NEW_EDITION, ["aibl-my-own.md"]))
        applied = self.apply(fresh)
        self.assertEqual((applied["applied"]["errors"], applied["applied"]["copied"]), ([], NEW_EDITION))
        # an edited agent in the shallow clone is still the student's
        self.write(fresh / ".claude" / "agents" / "aibl-hatch.md", b"changed here\n")
        self.commit(fresh, "my hatch")
        self.assertEqual(self.report(fresh)["name_conflict"], ["aibl-hatch.md"])

    def test_a_manifest_from_anywhere_else_proves_nothing(self):
        wb = self.workbench("fix")
        self.write_manifest(wb, repository="someone-else/agent-workforce")
        self.commit(wb, "a manifest that is not the program's")
        self.git(wb, "remote", "remove", "agent-workforce")
        self.assertEqual(self.report(wb)["status"], "no_agents")

    # --- a name alone proves nothing: a course name with bytes the course never published ---

    def placed(self):
        f = self.home / ".claude" / "aibl-agent-menu-placed.json"
        return json.loads(f.read_text()) if f.exists() else {"agents": {}}

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
        # and it stays the student's on every later run
        self.apply(wb)
        self.assertEqual((self.menu / "aibl-hatch.md").read_bytes(), mine)

    def test_a_workbench_agent_with_a_course_name_but_not_course_bytes_is_the_students(self):
        # an old-edition workbench has the student's own aibl-hatch.md; the fetched edition ships one
        mine = b"my own hatch, in my workbench\n"
        wb = self.workbench("old")
        self.write(wb / ".claude" / "agents" / "aibl-hatch.md", mine)
        self.commit(wb, "my own hatch")
        report = self.report(wb)
        self.assertEqual(report["name_conflict"], ["aibl-hatch.md"])
        self.assertIn("aibl-hatch.md", report["skipped"])
        self.assertNotIn("aibl-hatch.md", report["missing"])
        self.assertIn("name conflicts", self.hook_line(wb))
        applied = self.apply(wb)
        self.assertEqual(applied["applied"]["copied"], OLD_EDITION)
        self.assertFalse((self.menu / "aibl-hatch.md").exists())
        self.assertNotIn("aibl-hatch.md", self.placed()["agents"])
        # the student put their own copy in the menu themselves: settled, and never claimed
        self.write(self.menu / "aibl-hatch.md", mine)
        report = self.report(wb)
        self.assertEqual((report["name_conflict"], report["status"]), ([], "in_step"))
        self.apply(wb)
        self.assertNotIn("aibl-hatch.md", self.placed()["agents"])
        # later the workbench takes the course's aibl-hatch: the menu copy is still theirs, never
        # replaced without their own yes
        self.write(wb / ".claude" / "agents" / "aibl-hatch.md", body("aibl-hatch.md", "new"))
        self.commit(wb, "took the course's hatch")
        report = self.report(wb)
        self.assertEqual((report["edited"], report["changed"], report["name_conflict"]), (["aibl-hatch.md"], [], []))
        self.apply(wb)
        self.assertEqual((self.menu / "aibl-hatch.md").read_bytes(), mine)


if __name__ == "__main__":
    unittest.main()
