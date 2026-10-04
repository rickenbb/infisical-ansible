"""Verify that launching from another project preserves its Ansible context."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy


class LauncherTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".cache").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / ".cache")
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.inventory = self.project / "production.infisical.yml"
        self.inventory.write_text('''plugin: poc.infisical_pam.inventory
hosts:
  web01:
    account: /ssh/infitest/
  web02:
    account: ssh/infitest
  worker:
    account: production/second
''')
        self.playbook = self.project / "site.yml"
        self.playbook.write_text("- hosts: all\n  tasks: []\n")
        previous_cwd = Path.cwd()
        self.addCleanup(os.chdir, previous_cwd)
        environment = patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def args(self, *extra):
        return ["--project-dir", str(self.project), "--inventory", self.inventory.name,
                "--playbook", self.playbook.name, *extra]

    def test_requests_only_unique_accounts_and_preserves_project_options(self):
        os.environ["ANSIBLE_CONFIG"] = str(self.project / "custom.cfg")
        os.environ["ANSIBLE_COLLECTIONS_PATH"] = str(self.project / "collections")
        self.project.joinpath(".env").write_text("INFISICAL_URL=https://example.invalid\nPAM_REASON=release\n")
        extra = ["--extra-vars", "message=hello world; $(never-run)"]
        with patch("deploy.shutil.which", side_effect=lambda name: f"/tools/{name}"), \
             patch("deploy.os.execv") as execute:
            deploy.main(self.args("--args-json", json.dumps(extra), "--", "--check", "--limit", "web01"))
        binary, command = execute.call_args.args
        self.assertEqual(binary, "/tools/infisical")
        accounts = [command[i + 1] for i, value in enumerate(command) if value == "--account"]
        self.assertEqual(accounts, ["ssh/infitest", "production/second"])
        child = command[command.index("--") + 1:]
        self.assertEqual(child, ["/tools/ansible-playbook", "-i", str(self.inventory),
                                str(self.playbook), *extra, "--check", "--limit", "web01"])
        self.assertEqual(Path.cwd(), self.project)
        self.assertEqual(os.environ["ANSIBLE_CONFIG"], str(self.project / "custom.cfg"))
        self.assertEqual(os.environ["ANSIBLE_COLLECTIONS_PATH"], str(self.project / "collections"))
        self.assertEqual(command[command.index("--domain") + 1], "https://example.invalid")
        self.assertEqual(command[command.index("--reason") + 1], "release")

    def test_validate_only_does_not_start_tools_or_request_access(self):
        with patch("deploy.shutil.which") as lookup, patch("deploy.os.execv") as execute, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            deploy.main(self.args("--validate-only"))
        lookup.assert_not_called()
        execute.assert_not_called()
        self.assertIn("2 PAM account(s)", output.getvalue())

    def test_invalid_inputs_fail_before_requesting_access(self):
        cases = [
            self.args("--args-json", '{"invalid": true}'),
            self.args("--args-json", '[123]'),
            self.args("--playbook", "missing.yml"),
            self.args("--inventory", "hosts.yml"),
        ]
        with patch("deploy.os.execv") as execute, contextlib.redirect_stderr(io.StringIO()):
            for argv in cases:
                with self.subTest(argv=argv), self.assertRaises(SystemExit) as result:
                    deploy.main(argv)
                self.assertEqual(result.exception.code, 2)
        execute.assert_not_called()

    def test_invalid_account_is_rejected(self):
        for account in ("/", "ssh/../host", "ssh//host", "ssh/host\x01"):
            self.inventory.write_text("plugin: poc.infisical_pam.inventory\nhosts:\n  host:\n    account: "
                                      + json.dumps(account) + "\n")
            with self.subTest(account=account), self.assertRaises(ValueError):
                deploy.inventory_accounts(self.inventory)

    def test_installed_collection_works_from_callers_config(self):
        # Install through Ansible's normal collection mechanism, then execute
        # the real child command with a fixture in place of a live PAM session.
        os.environ["ANSIBLE_LOCAL_TEMP"] = str(self.project / "tmp")
        result = subprocess.run([str(ROOT / ".venv/bin/ansible-galaxy"), "collection", "install",
                                 str(ROOT / "plugin/ansible_collections/poc/infisical_pam"),
                                 "-p", str(self.project / "collections"), "--force"],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.project.joinpath("ansible.cfg").write_text('''[defaults]
collections_path = ./collections
[inventory]
unparsed_is_failed = True
any_unparsed_is_failed = True
''')
        self.project.joinpath("group_vars").mkdir()
        self.project.joinpath("group_vars/all.yml").write_text("project_marker: from-caller\n")
        results = []
        find_executable = deploy.shutil.which
        pam_stub = str(self.project / "stub-infisical")

        def find_tool(name):
            # This offline test replaces the PAM parent below. Only Ansible
            # must be installed; do not depend on a local make tools run.
            return pam_stub if name == "infisical" else find_executable(name)

        def run_child(binary, command):
            self.assertEqual(binary, pam_stub)
            child = command[command.index("--") + 1:]
            env = dict(os.environ, INFISICAL_PAM_CONTEXT_FILE=str(ROOT / "tests/fixtures/context.md"))
            results.append(subprocess.run(child, env=env, text=True, capture_output=True))

        with patch("deploy.shutil.which", side_effect=find_tool), \
             patch("deploy.os.execv", side_effect=run_child):
            deploy.main(["--project-dir", str(self.project), "--inventory", self.inventory.name,
                         "--inventory-only"])
        self.assertEqual(results[0].returncode, 0, results[0].stderr)
        data = json.loads(results[0].stdout, object_hook=lambda obj: obj["__ansible_unsafe"]
                          if set(obj) == {"__ansible_unsafe"} else obj)
        self.assertEqual(data["_meta"]["hostvars"]["worker"]["ansible_port"], 52432)
        self.assertEqual(data["_meta"]["hostvars"]["worker"]["project_marker"], "from-caller")
        self.assertNotIn("ANSIBLE_CONFIG", os.environ)
        self.assertNotIn("ANSIBLE_COLLECTIONS_PATH", os.environ)


if __name__ == "__main__":
    unittest.main()
