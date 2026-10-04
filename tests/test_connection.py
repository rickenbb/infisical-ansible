"""Exercise Ansible's SSH/sudo protocol with a transport that drops stderr."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class PAMConnectionTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".cache").mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=ROOT / ".cache")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.ssh = self.project / "ssh-without-stderr"
        # Execute the remote command locally, retaining stdin/stdout while
        # dropping stderr just as the pinned gateway does. No network or sudo
        # privileges are needed; the real Ansible SSH state machine still runs.
        self.ssh.write_text(f"#!{sys.executable}\n" + '''import os
import sys
with open(os.devnull, "wb") as sink:
    os.dup2(sink.fileno(), 2)
os.execv("/bin/sh", ["/bin/sh", "-c", sys.argv[-1]])
''')
        self.ssh.chmod(0o700)
        self.sudo = self.project / "sudo-prompt"
        self.sudo.write_text(f"#!{sys.executable}\n" + '''import os
import sys
args = sys.argv[1:]
prompt = args[args.index("-p") + 1]
os.write(2, prompt.encode())
# Read exactly one password line, leaving the pipelined module on stdin.
password = bytearray()
while True:
    byte = os.read(0, 1)
    if not byte or byte == b"\\n":
        break
    password.extend(byte)
if password != b"offline-test-password":
    os.write(2, b"Sorry, try again.\\n")
    sys.exit(1)
command = args[args.index("-u") + 2:]
os.execv(command[0], command)
''')
        self.sudo.chmod(0o700)
        self.inventory = self.project / "test.infisical.yml"
        self.inventory.write_text(yaml.safe_dump({
            "plugin": "poc.infisical_pam.inventory",
            "hosts": {"target": {
                "account": "ssh/infitest",
                "vars": {
                    "ansible_ssh_executable": str(self.ssh),
                    "ansible_python_interpreter": sys.executable,
                    "ansible_become_exe": str(self.sudo),
                    "ansible_become_password": "offline-test-password",
                    "ansible_ssh_timeout": 1,
                },
            }},
        }))

    def run_playbook(self, tasks, variables=None):
        playbook = self.project / "site.yml"
        playbook.write_text(yaml.safe_dump([{
            "hosts": "all", "gather_facts": False, "tasks": tasks,
        }]))
        env = dict(os.environ, ANSIBLE_CONFIG=str(ROOT / "ansible.cfg"),
                   ANSIBLE_COLLECTIONS_PATH=str(ROOT / "plugin"),
                   ANSIBLE_LOCAL_TEMP=str(self.project / "tmp"),
                   INFISICAL_PAM_CONTEXT_FILE=str(ROOT / "tests/fixtures/context.md"),
                   OBJC_DISABLE_INITIALIZE_FORK_SAFETY="YES")
        return subprocess.run([
            str(ROOT / ".venv/bin/ansible-playbook"), "-i", str(self.inventory),
            str(playbook), "--extra-vars", json.dumps({
                "ansible_ssh_retries": 0, **(variables or {}),
            }),
        ], cwd=self.project, env=env, text=True, capture_output=True, timeout=30)

    def test_password_sudo_with_pipelining_survives_missing_stderr(self):
        tasks = [{
            "name": "Run a pipelined module after the sudo password exchange",
            "ansible.builtin.command": {"argv": ["/bin/echo", "through-pam"]},
            "become": True,
            "register": "command_result",
        }, {
            "ansible.builtin.assert": {"that": ["command_result.stdout == 'through-pam'"]},
        }]
        broken = self.run_playbook(tasks, {"ansible_connection": "ansible.builtin.ssh"})
        self.assertNotEqual(broken.returncode, 0)
        self.assertIn("waiting for privilege escalation prompt", broken.stdout + broken.stderr)
        fixed = self.run_playbook(tasks)
        self.assertEqual(fixed.returncode, 0, fixed.stdout + fixed.stderr)

    def test_incorrect_sudo_password_reports_error(self):
        result = self.run_playbook([{
            "ansible.builtin.command": {"argv": ["/bin/echo", "must-not-run"]},
            "become": True,
        }], {"ansible_become_password": "wrong-password"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Incorrect sudo password", result.stdout + result.stderr)
        self.assertNotIn("waiting for privilege escalation prompt", result.stdout + result.stderr)

    def test_task_diagnostics_and_return_code_survive_missing_stderr(self):
        result = self.run_playbook([{
            "ansible.builtin.raw": "printf 'remote diagnostic\\n' >&2; exit 7 # trailing comment",
            "register": "command_result",
            "failed_when": False,
        }, {
            "ansible.builtin.assert": {"that": [
                "command_result.rc == 7",
                "'remote diagnostic' in command_result.stdout",
            ]},
        }])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_piped_file_transfers_preserve_binary_contents(self):
        source = self.project / "source.bin"
        destination = self.project / "remote.bin"
        fetched = self.project / "fetched.bin"
        contents = bytes(range(256)) * 32
        source.write_bytes(contents)
        result = self.run_playbook([{
            "ansible.builtin.copy": {"src": str(source), "dest": str(destination), "mode": "0600"},
        }, {
            "ansible.builtin.fetch": {"src": str(destination), "dest": str(fetched), "flat": True},
        }])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(destination.read_bytes(), contents)
        self.assertEqual(fetched.read_bytes(), contents)


if __name__ == "__main__":
    unittest.main()
