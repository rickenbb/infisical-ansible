"""Exercise the actual Ansible loader and fail-closed behavior, without PAM credentials."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin"))
from ansible_collections.poc.infisical_pam.plugins.module_utils.context import (
    ContextError, parse_context, resolve_account,
)

FIXTURE = ROOT / "tests/fixtures/context.md"


def inventory_json(output):
    # Ansible 2.19 serializes untrusted strings with an explicit JSON wrapper.
    return json.loads(output, object_hook=lambda obj: obj["__ansible_unsafe"]
                      if set(obj) == {"__ansible_unsafe"} else obj)


class ContextTests(unittest.TestCase):
    def test_account_mapping_and_leading_slash(self):
        accounts = parse_context(FIXTURE.read_text())
        self.assertEqual(resolve_account(accounts, "/production/second").port, 52432)
        self.assertEqual(resolve_account(accounts, "ssh/infitest").port, 52431)
        self.assertNotIn("production/database", accounts)

    def test_missing_and_approval_gated_accounts_fail(self):
        accounts = parse_context(FIXTURE.read_text())
        for name in ("unknown", "production/database", "production/pending"):
            with self.subTest(name=name), self.assertRaises(ContextError):
                resolve_account(accounts, name)

    def test_ambiguous_or_unsafe_context_fails(self):
        documents = [
            "## web (SSH)\n- Host: 192.168.1.1, port 22\n",
            "## web (SSH)\n- Host: 127.0.0.1, port 0\n",
            "## web (SSH)\n- Host: 127.0.0.1, port 65536\n",
            "## web (SSH)\n- Endpoint: 127.0.0.1:22\n",
            "## web (SSH)\n- Host: 127.0.0.1, port 22\n" * 2,
            "## web (SSH)\n" + "- Host: 127.0.0.1, port 22\n" * 2,
        ]
        for document in documents:
            with self.subTest(document=document), self.assertRaises(ContextError):
                parse_context(document)


class AnsibleIntegrationTests(unittest.TestCase):
    def run_inventory(self, content=None, context=FIXTURE):
        env = dict(os.environ, ANSIBLE_CONFIG=str(ROOT / "ansible.cfg"),
                   ANSIBLE_COLLECTIONS_PATH=str(ROOT / "plugin"),
                   ANSIBLE_LOCAL_TEMP=str(ROOT / ".cache/test-ansible"))
        env.pop("INFISICAL_PAM_CONTEXT_FILE", None)
        if context:
            env["INFISICAL_PAM_CONTEXT_FILE"] = str(context)
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as directory:
            inventory = Path(directory) / "test.infisical.yml"
            inventory.write_text(content or (ROOT / "example/inventory.infisical.yml").read_text())
            return subprocess.run([str(ROOT / ".venv/bin/ansible-inventory"), "-i", str(inventory), "--list"],
                                  cwd=ROOT, env=env, text=True, capture_output=True)

    @classmethod
    def setUpClass(cls):
        (ROOT / ".cache").mkdir(exist_ok=True)

    def test_real_ansible_loader_resolves_groups_variables_and_transport(self):
        result = self.run_inventory()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = inventory_json(result.stdout)
        host = data["_meta"]["hostvars"]["nfitest"]
        self.assertEqual(host["ansible_host"], "127.0.0.1")
        self.assertEqual(host["ansible_port"], 52431)
        self.assertEqual(host["ansible_user"], "pam")
        self.assertEqual(host["ansible_connection"], "poc.infisical_pam.ssh")
        self.assertEqual(host["ansible_remote_tmp"], "/tmp")
        self.assertFalse(host["ansible_ssh_use_tty"])
        self.assertFalse(host["ansible_become"])
        self.assertEqual(data["web"]["hosts"], ["nfitest"])

    def test_multi_host_inventory_keeps_application_variables(self):
        result = self.run_inventory('''plugin: poc.infisical_pam.inventory
vars:
  app_name: sample
hosts:
  one:
    account: ssh/infitest
    groups: [web, staging]
    vars:
      ansible_host: must-be-overridden
  two:
    account: production/second
    groups: [web]
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = inventory_json(result.stdout)
        hosts = data["_meta"]["hostvars"]
        self.assertEqual(hosts["one"]["ansible_host"], "127.0.0.1")
        self.assertEqual(hosts["two"]["ansible_port"], 52432)
        self.assertEqual(hosts["two"]["app_name"], "sample")

    def test_missing_context_is_a_nonzero_exit(self):
        result = self.run_inventory(context=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("INFISICAL_PAM_CONTEXT_FILE is unset", result.stderr)

    def test_missing_host_fails_entire_inventory(self):
        result = self.run_inventory('''plugin: poc.infisical_pam.inventory
hosts:
  first:
    account: ssh/infitest
  missing:
    account: unknown
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing from PAM context", result.stderr)

    def test_nginx_playbook_syntax(self):
        env = dict(os.environ, INFISICAL_PAM_CONTEXT_FILE=str(FIXTURE),
                   ANSIBLE_LOCAL_TEMP=str(ROOT / ".cache/test-ansible"))
        result = subprocess.run([str(ROOT / ".venv/bin/ansible-playbook"), "-i",
                                 "example/inventory.infisical.yml", "example/nginx.yml", "--syntax-check"],
                                cwd=ROOT, env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
