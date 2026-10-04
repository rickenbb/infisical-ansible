#!/usr/bin/env python3
"""Run a project's Ansible playbook inside the PAM session its inventory needs."""

import argparse
import json
import os
from pathlib import Path
import shutil

import yaml
from settings import load_settings


def inventory_accounts(inventory):
    config = yaml.safe_load(inventory.read_text(encoding="utf-8"))
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
        account = account.strip().strip("/")
        if not account or any(part in ("", ".", "..") for part in account.split("/")):
            raise ValueError("PAM account must be a valid folder/account path")
        if any(ord(char) < 32 for char in account):
            raise ValueError("PAM account contains a control character")
        if account not in accounts:
            accounts.append(account)
    return accounts


def main(argv=None):
    # Resolve the project before reading its .env; support files can live in a
    # different checkout without redirecting the caller's Ansible configuration.
    project_parser = argparse.ArgumentParser(add_help=False)
    project_parser.add_argument("--project-dir", default=str(Path.cwd()))
    project_args, _ = project_parser.parse_known_args(argv)
    project = Path(project_args.project_dir).resolve()
    try:
        os.chdir(project)
    except OSError as exc:
        project_parser.error(f"Cannot use project directory: {exc}")
    load_settings(project)
    parser = argparse.ArgumentParser(description=__doc__, parents=[project_parser])
    parser.add_argument("--inventory", default=os.environ.get("PAM_INVENTORY"))
    parser.add_argument("--playbook", default=os.environ.get("PAM_PLAYBOOK"))
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--validate-only", action="store_true", help="validate inputs without PAM access")
    parser.add_argument("--args-json", default=os.environ.get("PAM_ARGS_JSON", "[]"),
                        help="JSON array of additional Ansible arguments (no shell evaluation)")
    args, ansible_args = parser.parse_known_args(argv)
    if ansible_args[:1] == ["--"]:
        ansible_args = ansible_args[1:]
    try:
        if not os.environ["INFISICAL_DOMAIN"].strip():
            raise ValueError("Set a nonempty INFISICAL_DOMAIN")
        if not args.inventory:
            raise ValueError("Set --inventory or PAM_INVENTORY")
        inventory = Path(args.inventory).resolve()
        if not str(inventory).endswith((".infisical.yml", ".infisical.yaml")):
            raise ValueError("Inventory filename must end in .infisical.yml or .infisical.yaml")
        accounts = inventory_accounts(inventory)
        extra = json.loads(args.args_json)
        if not isinstance(extra, list) or any(not isinstance(value, str) or "\0" in value for value in extra):
            raise ValueError("--args-json must be a JSON array of strings")
        ansible_args = [*extra, *ansible_args]
        if not args.inventory_only:
            if not args.playbook:
                raise ValueError("Set --playbook or PAM_PLAYBOOK")
            playbook = Path(args.playbook).resolve()
            if not playbook.is_file():
                raise ValueError(f"Playbook does not exist: {playbook}")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.error(str(exc))
    if args.validate_only:
        print(f"Validated inventory with {len(accounts)} PAM account(s); no access requested")
        return

    infisical = shutil.which("infisical")
    executable = "ansible-inventory" if args.inventory_only else "ansible-playbook"
    ansible = shutil.which(executable)
    if not infisical or not ansible:
        parser.error(f"Install Infisical CLI 0.43.132 and {executable}, and ensure both are on PATH")
    # Let Ansible discover the caller's config and installed collections normally.
    os.environ.setdefault("ANSIBLE_LOCAL_TEMP", str(project / ".cache/ansible/tmp"))
    os.environ["ANSIBLE_INVENTORY_UNPARSED_IS_FAILED"] = "true"
    os.environ["ANSIBLE_INVENTORY_ANY_UNPARSED_IS_FAILED"] = "true"
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    Path(os.environ["ANSIBLE_LOCAL_TEMP"]).mkdir(parents=True, exist_ok=True)
    command = [infisical, "pam", "agentic", "access", "--agent", "generic",
               "--domain", os.environ["INFISICAL_DOMAIN"],
               "--reason", os.environ.get("PAM_REASON", "Ansible deployment"),
               "--no-approval-request"]
    for account in accounts:
        command.extend(["--account", account])
    if os.environ.get("PAM_LOG_FILE"):
        command.extend(["--log-file", os.environ["PAM_LOG_FILE"]])
    if args.inventory_only:
        child = [ansible, "-i", str(inventory), "--list", *ansible_args]
    else:
        child = [ansible, "-i", str(inventory), str(playbook), *ansible_args]
    os.execv(infisical, [*command, "--", *child])


if __name__ == "__main__":
    main()
