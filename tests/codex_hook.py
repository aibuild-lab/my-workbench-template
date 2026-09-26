"""The Codex twin of the update check: .codex/hooks.json runs the same script Claude runs, and the
script answers Codex's SessionStart payload the way Codex reads it (hookSpecificOutput.additionalContext).
Proven live with Codex 0.156.1 on 09-26-2026: `hook: SessionStart Completed` and the notice in the reply."""
import json, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CodexHook(unittest.TestCase):
    def test_codex_runs_the_same_script(self):
        config = json.loads((ROOT / ".codex/hooks.json").read_text(encoding="utf-8"))
        groups = config["hooks"]["SessionStart"]
        commands = [h["command"] for g in groups for h in g["hooks"] if h.get("type") == "command"]
        self.assertEqual(commands, ["node .claude/hooks/update-check.mjs"])
        self.assertTrue((ROOT / ".claude/hooks/update-check.mjs").is_file())
        # No matcher: the script itself keeps to new conversations (startup, clear).
        self.assertFalse(any("matcher" in g for g in groups))

    def test_codex_payload_outside_a_workbench_stays_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            payload = {"session_id": "t", "transcript_path": None, "cwd": d, "hook_event_name": "SessionStart",
                       "model": "m", "permission_mode": "default", "source": "startup"}
            r = subprocess.run(["node", str(ROOT / ".claude/hooks/update-check.mjs")], input=json.dumps(payload),
                               cwd=d, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(r.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
