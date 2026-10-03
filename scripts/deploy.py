#!/usr/bin/env python3
"""Demo launcher: request exactly the accounts declared in the plugin inventory."""

import os
from pathlib import Path
import shutil
import sys

import yaml
from settings import load_settings

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    load_settings()
    inventory = Path(os.environ.get("PAM_INVENTORY", "example/inventory.infisical.yml"))
    try:
        config = yaml.safe_load(inventory.read_text())
        if not isinstance(config, dict) or config.get("plugin") != "poc.infisical_pam.inventory":
            raise ValueError("Expected a poc.infisical_pam.inventory configuration")
        hosts = config.get("hosts")
        if not isinstance(hosts, dict) or not hosts:
            raise ValueError("Inventory hosts must be a nonempty mapping")
        accounts = []
        for host in hosts.values():
            account = host.get("account") if isinstance(host, dict) else None
            if not isinstance(account, str) or not account.strip():
                raise ValueError("Every inventory host needs a PAM account")
            if account not in accounts:
                accounts.append(account)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        sys.exit(f"Inventory error: {exc}")

    infisical = shutil.which("infisical")
    if not infisical:
        sys.exit("Install Infisical CLI 0.43.132 and ensure infisical is on PATH")
    os.environ["ANSIBLE_CONFIG"] = str(ROOT / "ansible.cfg")
    os.environ["ANSIBLE_COLLECTIONS_PATH"] = str(ROOT / "plugin")
    # Keep controller writes inside the workspace, allowed by Infisical's sandbox.
    os.environ["ANSIBLE_LOCAL_TEMP"] = str(ROOT / ".cache/ansible/tmp")
    os.environ["ANSIBLE_INVENTORY_UNPARSED_IS_FAILED"] = "true"
    os.environ["ANSIBLE_INVENTORY_ANY_UNPARSED_IS_FAILED"] = "true"
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    (ROOT / ".cache/ansible/tmp").mkdir(parents=True, exist_ok=True)
    command = [infisical, "pam", "agentic", "access", "--agent", "generic",
               "--domain", os.environ.get("INFISICAL_DOMAIN", "https://infisical.zh.rickenbacher.tech"),
               "--reason", os.environ.get("PAM_REASON", "Ansible nginx proof of concept"),
               "--no-approval-request"]
    for account in accounts:
        command.extend(["--account", account])
    if os.environ.get("PAM_LOG_FILE"):
        command.extend(["--log-file", os.environ["PAM_LOG_FILE"]])
    args = sys.argv[1:]
    if args == ["--inventory-only"]:
        child = [str(ROOT / ".venv/bin/ansible-inventory"), "-i", str(inventory), "--list"]
    else:
        child = [str(ROOT / ".venv/bin/ansible-playbook"), "-i", str(inventory),
                 "example/nginx.yml", *args]
    os.execv(infisical, [*command, "--", *child])


if __name__ == "__main__":
    main()
