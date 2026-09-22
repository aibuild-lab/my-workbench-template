"""Synthetic local-Git rehearsal; no student account, app, or installation claim."""
import json, os, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class Transition(unittest.TestCase):
    def test_enrollment_update_and_personalization(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            def git(repo, *args, ok=True):
                p = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True)
                if ok: self.assertEqual(p.returncode, 0, p.stderr)
                return p
            def init(name, branch="main"):
                p = base/name; p.mkdir(); git(p,"init","-q","-b",branch)
                git(p,"config","user.name","Fixture"); git(p,"config","user.email","fixture@example.invalid")
                return p
            def write(repo, name, body):
                p=repo/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(body)
            def commit(repo, msg):
                git(repo,"add","."); git(repo,"commit","-qm",msg)
            chief=".claude/agents/aibl-chief-of-staff.md"
            course=init("course","student")
            original="# Chief, your Chief of Staff\n\nPlan first.\n\nKeep sources.\n"
            write(course,chief,original)
            write(course,"course/workforce/welcome.md","Fixture welcome\n")
            commit(course,"edition one")
            for packaged in (False, True):
                wb=init("package" if packaged else "fresh")
                write(wb,"context/project.md","My private project\n")
                write(wb,".claude/settings.json",'{"hooks":{"Other":[]}}\n')
                write(wb,".aibl/template.json",'{"fixture":true}\n')
                if packaged:
                    write(wb,chief,original)
                    write(wb,".aibl/family.json",'{"synthetic_historical_receipt":true}\n')
                commit(wb,"existing Essentials fixture")
                protected={p:p.read_bytes() for p in wb.rglob("*") if p.is_file() and ".git" not in p.parts and str(p.relative_to(wb))!=chief}
                # Official URL, local-only transport rewrite for the synthetic test.
                git(wb,"config",f"url.{course}.insteadOf","https://github.com/aibuild-lab/agent-workforce.git")
                git(wb,"remote","add","agent-workforce","https://github.com/aibuild-lab/agent-workforce.git")
                git(wb,"fetch","-q","agent-workforce","student")
                self.assertNotEqual(git(wb,"merge-base","HEAD","agent-workforce/student",ok=False).returncode,0)
                # Merge is executed only after the fixture's explicit approval point.
                git(wb,"merge","--allow-unrelated-histories","--no-ff","--no-commit","agent-workforce/student")
                git(wb,"commit","-qm","Approved enrollment")
                before=git(wb,"rev-parse","HEAD").stdout
                git(wb,"merge","--allow-unrelated-histories","--no-edit","agent-workforce/student")
                self.assertEqual(before,git(wb,"rev-parse","HEAD").stdout)
                for p, data in protected.items(): self.assertEqual(p.read_bytes(),data)
            # Personalization plus a nonoverlapping program change survives merge.
            wb=base/"package"
            write(wb,chief,original.replace("# Chief,", "# Ada,")); commit(wb,"Personal name")
            write(course,chief,original.replace("Keep sources.","Keep approved sources.")); commit(course,"Better source rule")
            git(wb,"fetch","-q","agent-workforce","student"); git(wb,"merge","--no-edit","agent-workforce/student")
            self.assertIn("# Ada,",(wb/chief).read_text()); self.assertIn("approved sources",(wb/chief).read_text())
            # Same-line conflict: abort keeps personalization, explicit combination keeps both.
            write(course,chief,(course/chief).read_text().replace("# Chief,","# Program Chief,"));commit(course,"New default name")
            git(wb,"fetch","-q","agent-workforce","student")
            clean=git(wb,"rev-parse","HEAD").stdout
            self.assertNotEqual(git(wb,"merge","--no-ff","--no-commit","agent-workforce/student",ok=False).returncode,0)
            git(wb,"merge","--abort"); self.assertEqual(clean,git(wb,"rev-parse","HEAD").stdout)
            git(wb,"merge","--no-ff","--no-commit","agent-workforce/student",ok=False)
            git(wb,"checkout","--theirs","--",chief)
            write(wb,chief,(wb/chief).read_text().replace("# Program Chief,","# Ada,"))
            git(wb,"add","--",chief);git(wb,"commit","-qm","Approved program improvements with Ada retained")
            self.assertIn("# Ada,",(wb/chief).read_text())
            self.assertEqual((wb/"context/project.md").read_text(),"My private project\n")
            # Read-only check ignores unrelated remotes and rejects wrong program targets.
            git(wb,"remote","add","unrelated","https://invalid.example/never-fetch")
            git(wb,"remote","set-url","agent-workforce","https://invalid.example/wrong")
            env={**os.environ,"CLAUDE_PROJECT_DIR":str(wb)}
            p=subprocess.run(["node",str(ROOT/".claude/hooks/update-check.mjs"),"--json"],cwd=wb,env=env,text=True,capture_output=True,check=True)
            report=json.loads(p.stdout)
            self.assertEqual(len(report["programs"]),1)
            self.assertEqual(report["programs"][0]["error"],"remote_mismatch")
            git(wb,"remote","set-url","agent-workforce","https://github.com/aibuild-lab/agent-workforce.git")
            p=subprocess.run(["node",str(ROOT/".claude/hooks/update-check.mjs"),"--json"],cwd=wb,env=env,text=True,capture_output=True,check=True)
            report=json.loads(p.stdout)
            # git get-url expands insteadOf; production accepts only official resolved URLs.
            self.assertEqual(report["programs"][0]["error"],"remote_mismatch")

    def test_core_refresh_preserves_settings_and_kept_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            def git(root,*args):
                return subprocess.run(["git","-C",str(root),*args],text=True,capture_output=True,check=True).stdout
            def seed(name):
                p=base/name;p.mkdir();git(p,"init","-q","-b","main")
                git(p,"config","user.name","Fixture");git(p,"config","user.email","fixture@example.invalid")
                return p
            def put(root,path,text):
                p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            template=seed("template");wb=seed("older-workbench")
            kept=".claude/skills/aibl-personalize/SKILL.md"
            updated=".claude/skills/aibl-enroll/SKILL.md"
            for root,word in ((template,"template"),(wb,"student")):
                put(root,kept,word);put(root,updated,word)
                put(root,".claude/settings.json",json.dumps({"student":word}))
                git(root,"add",".");git(root,"commit","-qm","seed")
            settings=(wb/".claude/settings.json").read_bytes()
            git(wb,"remote","add","template",str(template));git(wb,"fetch","-q","template","main")
            # Student chooses keep personalize, take enroll, leave settings.
            git(wb,"checkout","template/main","--",updated)
            git(wb,"commit","-qm","Approved skill refresh")
            self.assertEqual((wb/kept).read_text(),"student")
            self.assertEqual((wb/updated).read_text(),"template")
            self.assertEqual((wb/".claude/settings.json").read_bytes(),settings)
            put(wb,"unfinished.md","keep me")
            self.assertTrue(git(wb,"status","--porcelain","--untracked-files=all"))

    def test_client_skill_parity(self):
        for skill in ("aibl-enroll","aibl-update"):
            self.assertEqual((ROOT/f".claude/skills/{skill}/SKILL.md").read_bytes(),(ROOT/f".agents/skills/{skill}/SKILL.md").read_bytes())

if __name__ == "__main__": unittest.main()
