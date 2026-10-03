"""Expose active Infisical PAM SSH proxies as normal Ansible inventory hosts."""

from pathlib import Path
import re

from ansible.errors import AnsibleParserError
from ansible.plugins.inventory import BaseInventoryPlugin
from ansible_collections.poc.infisical_pam.plugins.module_utils.context import (
    ContextError, parse_context, resolve_account,
)

DOCUMENTATION = r'''
name: inventory
plugin_type: inventory
short_description: Resolve SSH hosts through active Infisical PAM proxies
description:
  - Reads the Markdown context created by C(infisical pam agentic access).
  - No API calls, credentials, proxy lifecycle, or persistent endpoint cache.
  - Supports the context format emitted by Infisical CLI 0.43.132.
author: infisical-ansible contributors
options:
  plugin:
    description: Name of this inventory plugin.
    required: true
    choices: [poc.infisical_pam.inventory]
  context_file:
    description: Live context file supplied to the Infisical child process.
    type: path
    env:
      - name: INFISICAL_PAM_CONTEXT_FILE
  hosts:
    description:
      - Map of host aliases to dictionaries with C(account), optional C(groups), and optional C(vars).
      - Every host must resolve to a live SSH account before any hosts are added.
    type: dict
    required: true
  vars:
    description: Variables applied to the all group.
    type: dict
    default: {}
'''

EXAMPLES = r'''
plugin: poc.infisical_pam.inventory
hosts:
  web01:
    account: servers/web01
    groups: [web]
    vars:
      ansible_become: true
'''

# These flags apply only to loopback PAM proxies. Avoid personal SSH config,
# agent credentials, and Unix control sockets blocked by Infisical's sandbox.
SSH_ARGS = " ".join([
    "-F /dev/null", "-o BatchMode=yes", "-o ConnectTimeout=20",
    "-o StrictHostKeyChecking=no", "-o UserKnownHostsFile=/dev/null",
    "-o GlobalKnownHostsFile=/dev/null", "-o IdentityAgent=none",
    "-o IdentitiesOnly=yes", "-o PubkeyAuthentication=no",
    "-o PasswordAuthentication=no", "-o KbdInteractiveAuthentication=no",
    "-o ControlMaster=no", "-o ControlPath=none",
    "-o ServerAliveInterval=15", "-o ServerAliveCountMax=3",
])


class InventoryModule(BaseInventoryPlugin):
    NAME = "poc.infisical_pam.inventory"

    def verify_file(self, path):
        return super().verify_file(path) and path.endswith((".infisical.yml", ".infisical.yaml"))

    def parse(self, inventory, loader, path, cache=True):
        super().parse(inventory, loader, path, cache=False)
        self._read_config_data(path)
        context_file = self.get_option("context_file")
        if not context_file:
            raise AnsibleParserError("INFISICAL_PAM_CONTEXT_FILE is unset; run Ansible inside infisical pam agentic access")
        try:
            endpoints = parse_context(Path(context_file).read_text(encoding="utf-8"))
            hosts = self.get_option("hosts")
            if not hosts:
                raise ContextError("hosts must contain at least one host")
            resolved = []
            for alias, spec in hosts.items():
                if not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", alias):
                    raise ContextError("Invalid inventory host alias")
                if not isinstance(spec, dict) or set(spec) - {"account", "groups", "vars"}:
                    raise ContextError(f"{alias}: expected account, optional groups and vars")
                endpoint = resolve_account(endpoints, spec.get("account"))
                groups = spec.get("groups", [])
                if not isinstance(groups, list) or any(
                    not isinstance(g, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", g)
                    or g in ("all", "ungrouped") for g in groups
                ):
                    raise ContextError(f"{alias}: groups must be a list of valid group names")
                variables = spec.get("vars", {})
                if not isinstance(variables, dict) or any(not isinstance(k, str) for k in variables):
                    raise ContextError(f"{alias}: vars must be a mapping with string keys")
                resolved.append((alias, endpoint, groups, variables))
        except (OSError, UnicodeError, ContextError) as exc:
            raise AnsibleParserError(str(exc)) from exc

        for key, value in self.get_option("vars").items():
            self.inventory.set_variable("all", key, value)
        for alias, endpoint, groups, variables in resolved:
            self.inventory.add_host(alias)
            for group in groups:
                self.inventory.add_group(group)
                self.inventory.add_host(alias, group=group)
            for key, value in variables.items():
                self.inventory.set_variable(alias, key, value)
            for key, value in {
                "infisical_pam_account": endpoint.account,
                "ansible_connection": "ssh",
                "ansible_host": endpoint.host,
                "ansible_port": endpoint.port,
                "ansible_user": "pam",
                "ansible_ssh_args": SSH_ARGS,
                "ansible_ssh_common_args": "",
                "ansible_ssh_extra_args": "",
                "ansible_ssh_transfer_method": "piped",
                "ansible_ssh_use_tty": False,
                "ansible_ssh_retries": 2,
                "ansible_pipelining": True,
                # "pam" is only a proxy placeholder. Expanding ~pam on the
                # target can fail/hang because the real OS user is different.
                # Ansible creates its own random, mode-0700 directory below /tmp.
                "ansible_remote_tmp": "/tmp",
            }.items():
                self.inventory.set_variable(alias, key, value)
