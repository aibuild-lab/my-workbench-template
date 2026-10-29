"""Agent Team HQ as a third program: enrollment's tree contract, a clean merge, the update check
and the agent menu.

Synthetic by default: a throwaway Agent Team HQ student branch, a clean workbench and a home
folder (HOME / USERPROFILE), so the real ~/.claude is never touched and no network is used.
The same tests, plus checks of the edition's own records, run against the real published edition
when AIBL_PUBLISHED_E8E36A38 points at a checkout of aibuild-lab/agent-team-hq whose `student`
branch is at e8e36a38 (the first Team HQ edition, 2026-10-13). That run is still offline: the
fixture fetch reads the checkout through an insteadOf rewrite, and the remote URL stays official.
No app, account, enrollment or installation claim.
"""
import json, os, stat, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import course_list  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "update-check.mjs"
ENROLL = [ROOT / ".claude" / "skills" / "aibl-enroll" / "SKILL.md", ROOT / ".agents" / "skills" / "aibl-enroll" / "SKILL.md"]
OFFICIAL = "https://github.com/aibuild-lab/agent-team-hq.git"
PUBLISHED_ENV = "AIBL_PUBLISHED_E8E36A38"
PUBLISHED_REVISION = "e8e36a38a308e22ddc7d3cbd209560bd5633324a"
# The current edition ships six (aibl-riff joined after the first); all six share Agent Workforce's names.
HQ_AGENTS = ["aibl-echo.md", "aibl-librarian.md", "aibl-riff.md", "aibl-scratch.md", "aibl-the-professor.md", "aibl-ygm.md"]
# The first published edition, e8e36a38, shipped five; the published-edition checks below pin it.
PUBLISHED_AGENTS = [n for n in HQ_AGENTS if n != "aibl-riff.md"]

# Step 4's reviewed paths for Agent Team HQ, as the skill states them.
HQ_PREFIXES = ("team-hq/", ".claude/agents/", ".codex/agents/", ".claude/skills/", ".agents/skills/")
HQ_EXACT = {".aibl/programs/agent-team-hq.json", ".aibl/course-agents.json"}
CORE_SKILLS = ("aibl-personalize", "aibl-checkpoint", "aibl-enroll", "aibl-update")
STEP_4_PATHS = ("Agent Team HQ: `team-hq/`, `.claude/agents/`, `.codex/agents/`, `.claude/skills/`, `.agents/skills/`, "
                "the one exact stamp `.aibl/programs/agent-team-hq.json`, and the program's list of its agents "
                "`.aibl/course-agents.json`.")
WORKFORCE = "https://github.com/aibuild-lab/agent-workforce.git"


def allowed(path):
    """Step 4 for Agent Team HQ: a listed prefix or exact stamp, never a template-owned core skill."""
    if any(path.startswith(f"{d}/skills/{s}/") for d in (".claude", ".agents") for s in CORE_SKILLS):
        return False
    return path in HQ_EXACT or path.startswith(HQ_PREFIXES)


class TeamHQ(unittest.TestCase):
    agents = HQ_AGENTS

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.course = self.base / "agent-team-hq"
        for name in self.agents:
            self.write(self.course / ".claude" / "agents" / name, f"---\nname: {name[:-3]}\n---\n{name} hq\n".encode())
            self.write(self.course / ".codex" / "agents" / (name[:-3] + ".toml"), f'name = "{name[:-3]}"\n'.encode())
        for d in (".claude", ".agents"):
            self.write(self.course / d / "skills" / "aibl-team-hq" / "SKILL.md", b"---\nname: aibl-team-hq\n---\nentry\n")
        self.write(self.course / "team-hq" / "CONTENTS.md", b"# Team HQ contents\n")
        self.write(self.course / ".aibl" / "programs" / "agent-team-hq.json", b"{}\n")
        self.git(self.course, "init", "-q", "-b", "student")
        course_list.write(self.course)
        self.commit(self.course, "Agent Team HQ student edition")
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), GIT_CONFIG_COUNT="1",
                        GIT_CONFIG_KEY_0="protocol.https.allow", GIT_CONFIG_VALUE_0="never", GIT_TERMINAL_PROMPT="0")

    def tearDown(self):
        for p in self.base.rglob("*"):
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
        self.git(repo, "add", "-A")
        self.git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", message)

    def workbench(self):
        """A clean workbench made from this template's files, with the program remote added and fetched."""
        wb = self.base / "workbench"
        for rel in ("AGENTS.md", "CLAUDE.md", ".aibl/template.json", "context/project.md", ".gitignore",
                    ".claude/settings.json", ".claude/hooks/update-check.mjs",
                    *[f"{d}/skills/{s}/SKILL.md" for d in (".claude", ".agents") for s in CORE_SKILLS]):
            self.write(wb / rel, (ROOT / rel).read_bytes())
        self.git(wb, "init", "-q", "-b", "main")
        self.commit(wb, "workbench")
        self.git(wb, "remote", "add", "agent-team-hq", OFFICIAL)
        # the remote's effective URL stays official; this one fetch reads the local fixture
        self.git(wb, "-c", f"url.{self.course}.insteadOf={OFFICIAL}", "fetch", "-q", "agent-team-hq",
                 "+student:refs/remotes/agent-team-hq/student")
        return wb

    def workforce_course(self):
        """A throwaway Workforce student branch whose six shared agents differ from Team HQ's."""
        wf = self.base / "agent-workforce"
        for name in self.agents + ["aibl-chief-of-staff.md"]:
            self.write(wf / ".claude" / "agents" / name, f"---\nname: {name[:-3]}\n---\n{name} workforce\n".encode())
        self.write(wf / ".aibl" / "programs" / "agent-workforce.json", b"{}\n")
        self.git(wf, "init", "-q", "-b", "student")
        course_list.write(wf)
        self.commit(wf, "Agent Workforce student edition")
        return wf

    def hook(self, wb, *args):
        p = subprocess.run(["node", str(HOOK), *args], text=True, capture_output=True,
                           env=dict(self.env, CLAUDE_PROJECT_DIR=str(wb)), cwd=str(wb))
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_workforce_after_team_hq_offers_the_workforce_helpers_as_course_copies(self):
        # Team HQ first, its helpers placed in the agent menu; then Workforce, taking the program's copies
        # of the shared files as step 4 recommends. The menu's Team HQ copies are course copies
        # ("changed", replaced on the one offer), never "edited", which would ask about each one.
        wb = self.workbench()
        self.git(wb, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "merge", "-q",
                 "--allow-unrelated-histories", "--no-ff", "-m", "Add Agent Team HQ", "agent-team-hq/student")
        preview = self.hook(wb, "--agent-menu")
        applied = self.hook(wb, "--agent-menu-apply", "--expect", preview["preview_sha256"])
        self.assertEqual(applied["status"], "in_step")
        self.assertEqual(sorted(p.name for p in (self.home / ".claude" / "agents").iterdir()), self.agents)
        wf = self.workforce_course()
        self.git(wb, "remote", "add", "agent-workforce", WORKFORCE)
        self.git(wb, "-c", f"url.{wf}.insteadOf={WORKFORCE}", "fetch", "-q", "agent-workforce",
                 "+student:refs/remotes/agent-workforce/student")
        subprocess.run(["git", "-C", str(wb), "merge", "-q", "--allow-unrelated-histories", "--no-ff", "--no-commit",
                        "agent-workforce/student"], capture_output=True)
        conflicts = self.git(wb, "diff", "--name-only", "--diff-filter=U").decode().split()
        self.assertEqual(sorted(conflicts), sorted([".aibl/course-agents.json"] + [f".claude/agents/{n}" for n in self.agents]))
        self.git(wb, "checkout", "--theirs", "--", *conflicts)
        self.git(wb, "add", "--", *conflicts)
        self.git(wb, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "Add Agent Workforce")
        menu = self.hook(wb, "--agent-menu")
        self.assertEqual(menu["edited"], [])
        self.assertEqual(sorted(menu["changed"]), self.agents)
        self.assertEqual(menu["missing"], ["aibl-chief-of-staff.md"])

    def test_skill_lists_team_hq_in_both_apps(self):
        for skill in ENROLL:
            text = skill.read_text()
            self.assertIn("| Agent Team HQ | agent-team-hq | https://github.com/aibuild-lab/agent-team-hq.git | student | aibl-team-hq |", text)
            # the test's allowed() below restates exactly this sentence of step 4
            self.assertIn(STEP_4_PATHS, text)
            self.assertIn("`.aibl/programs/agent-team-hq.json`", text)
            self.assertIn("A program not in this list stops before merging.", text)
        self.assertEqual(ENROLL[0].read_bytes(), ENROLL[1].read_bytes())

    def test_overlap_cost_is_said_honestly_in_both_apps(self):
        # B1 (rehearsal 88c39b3c): keeping the Workforce copies leaves the Workforce Professor, which teaches
        # Workforce lessons and never reads team-hq/. The cost line must say so and point at aibl-team-hq.
        update = [ROOT / d / "skills" / "aibl-update" / "SKILL.md" for d in (".claude", ".agents")]
        for skill in ENROLL + update:
            text = skill.read_text()
            self.assertNotIn("the Team HQ lessons still work with them", text, skill)
            self.assertIn("teaches the Agent Workforce lessons", text, skill)
            self.assertIn("the `aibl-team-hq` skill", text, skill)
        for skill in ENROLL:
            enroll = skill.read_text()
            self.assertIn("does not read the Team HQ lessons", enroll, skill)
            self.assertIn("Never say the Team HQ Professor or helpers are installed when the Workforce copies were kept.",
                          enroll, skill)

    def test_update_skill_knows_team_hq_in_both_apps(self):
        claude, codex = (ROOT / d / "skills" / "aibl-update" / "SKILL.md" for d in (".claude", ".agents"))
        self.assertEqual(claude.read_bytes(), codex.read_bytes())
        text = claude.read_text()
        self.assertIn("Agent Workforce and Agent Team HQ today", text)
        self.assertIn("`agent-team-hq.json`", text)
        self.assertIn("enrolled in both Agent Workforce and Agent Team HQ", text)

    def test_published_tree_is_within_step_4(self):
        wb = self.workbench()
        tree = self.git(wb, "ls-tree", "-r", "--name-only", "agent-team-hq/student").decode().split()
        self.assertTrue(tree)
        self.assertEqual([p for p in tree if not allowed(p)], [])
        for bad in ("CLAUDE.md", "AGENTS.md", ".claude/settings.json", "context/project.md",
                    ".claude/skills/aibl-enroll/SKILL.md", "lab/CONTENTS.md", ".aibl/programs/the-lab.json"):
            self.assertFalse(allowed(bad), bad)

    def test_clean_merge_keeps_personal_files_and_root_instructions(self):
        wb = self.workbench()
        before = {p: (wb / p).read_bytes() for p in ("AGENTS.md", "CLAUDE.md", "context/project.md", ".claude/settings.json")}
        self.git(wb, "merge", "--allow-unrelated-histories", "--no-ff", "--no-commit", "agent-team-hq/student")
        self.assertEqual(self.git(wb, "diff", "--cached", "--name-only", "--diff-filter=M").decode().split(), [])
        self.git(wb, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "Add Agent Team HQ")
        for p, data in before.items():
            self.assertEqual((wb / p).read_bytes(), data, p)
        self.assertTrue((wb / "team-hq" / "CONTENTS.md").is_file())
        self.assertTrue((wb / ".claude" / "skills" / "aibl-team-hq" / "SKILL.md").is_file())

    def test_update_check_reports_team_hq(self):
        wb = self.workbench()
        rows = [r for r in self.hook(wb, "--json")["programs"] if r["remote"] == "agent-team-hq"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "Agent Team HQ")
        self.assertNotEqual(rows[0]["error"], "remote_mismatch")  # https is off in the test: fetch_failed is expected

    def test_agent_menu_offers_team_hq_agents_after_enrollment(self):
        wb = self.workbench()
        self.git(wb, "merge", "--allow-unrelated-histories", "--no-ff", "-m", "Add Agent Team HQ", "agent-team-hq/student")
        menu = self.hook(wb, "--agent-menu")
        self.assertEqual(sorted(menu["missing"]), self.agents)


@unittest.skipUnless(os.environ.get(PUBLISHED_ENV),
                     f"set {PUBLISHED_ENV} to a checkout of aibuild-lab/agent-team-hq at e8e36a38")
class PublishedTeamHQ(TeamHQ):
    """Every TeamHQ test again, on the real published edition instead of the synthetic one."""
    agents = PUBLISHED_AGENTS

    def setUp(self):
        super().setUp()
        self.course = Path(os.environ[PUBLISHED_ENV]).resolve()
        tip = self.git(self.course, "rev-parse", "--verify", "refs/heads/student").decode().strip()
        self.assertEqual(tip, PUBLISHED_REVISION, f"{PUBLISHED_ENV}'s student branch is not the published e8e36a38")

    def test_fetched_edition_is_the_published_revision(self):
        wb = self.workbench()
        self.assertEqual(self.git(wb, "rev-parse", "agent-team-hq/student").decode().strip(), PUBLISHED_REVISION)

    def test_no_links_or_submodules(self):
        rows = self.git(self.course, "ls-tree", "-r", PUBLISHED_REVISION).decode().splitlines()
        self.assertTrue(rows)
        self.assertEqual([r for r in rows if r.split()[0] in ("120000", "160000")], [])

    def test_entry_skill_is_the_same_in_both_apps(self):
        claude, codex = (self.git(self.course, "show", f"{PUBLISHED_REVISION}:{d}/skills/aibl-team-hq/SKILL.md")
                         for d in (".claude", ".agents"))
        self.assertEqual(claude, codex)
        self.assertIn(b"name: aibl-team-hq", claude)

    def test_every_agent_has_a_codex_twin(self):
        tree = set(self.git(self.course, "ls-tree", "-r", "--name-only", PUBLISHED_REVISION).decode().split())
        agents = sorted(p.rsplit("/", 1)[-1] for p in tree if p.startswith(".claude/agents/"))
        self.assertEqual(agents, self.agents)
        for name in agents:
            self.assertIn(f".codex/agents/{name[:-3]}.toml", tree, name)

    def test_course_agent_list_is_what_the_publish_step_builds(self):
        shipped = json.loads(self.git(self.course, "show", f"{PUBLISHED_REVISION}:.aibl/course-agents.json"))
        clone = self.base / "edition"
        self.git(self.base, "clone", "-q", "--branch", "student", str(self.course), str(clone))
        self.assertEqual(shipped, course_list.build(clone))
        self.assertEqual(sorted(shipped["agents"]), self.agents)
        self.assertTrue(all(e["status"] == "current" for e in shipped["agents"].values()))

    def test_stamp_names_the_program_and_counts_the_tree(self):
        stamp = json.loads(self.git(self.course, "show", f"{PUBLISHED_REVISION}:.aibl/programs/agent-team-hq.json"))
        tree = self.git(self.course, "ls-tree", "-r", "--name-only", PUBLISHED_REVISION).decode().split()
        self.assertEqual(stamp["program"], "agent-team-hq")
        self.assertEqual(stamp["schema_version"], "aibl.program-stamp/v2")
        self.assertEqual(stamp["files"], len(tree))


if __name__ == "__main__":
    unittest.main()
