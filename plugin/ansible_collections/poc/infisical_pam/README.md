# Infisical PAM inventory (unofficial PoC)

Use `poc.infisical_pam.inventory` inside `infisical pam agentic access`.
The collection needs only Ansible and the context file supplied by Infisical;
it does not authenticate, start proxies, or depend on the demo scripts. The
inventory automatically selects its `poc.infisical_pam.ssh` connection adapter.

Install it with Ansible's standard collection installer from a built artifact,
a Git repository, or Galaxy/private Automation Hub after publication. The
repository's reusable `ansible-pam.yml` workflow installs it automatically;
the same plugin can be used on any supported Ansible controller.

```yaml
# collections/requirements.yml; replace main with a tested tag or commit.
collections:
  - name: https://github.com/rickenbb/infisical-ansible.git#/plugin/ansible_collections/poc/infisical_pam/
    type: git
    version: main
```

```sh
ansible-galaxy collection install -r collections/requirements.yml
```

```yaml
# inventory.infisical.yml
plugin: poc.infisical_pam.inventory
hosts:
  web01:
    account: servers/web01
    groups: [web]
    vars:
      ansible_become: true
```

```sh
infisical pam agentic access --account servers/web01 --reason deploy -- \
  ansible-playbook -i inventory.infisical.yml site.yml
```

See `ansible-doc -t inventory poc.infisical_pam.inventory` for options.
The connection adapter inherits Ansible's standard OpenSSH options; see
`ansible-doc -t connection poc.infisical_pam.ssh`. It redirects task stderr into
stdout on POSIX targets because the pinned Infisical gateway does not forward
SSH stderr. This keeps sudo password prompts and task diagnostics visible.
Supply `ansible_become_password` through your normal secret mechanism when
required. Pipelining and binary file transfers retain normal Ansible behavior;
remote task diagnostics appear in stdout.

`plugins/module_utils/context.py` is the only code coupled to Infisical's
Markdown format (CLI 0.43.132). Only loopback SSH endpoints are accepted.
SSH host-key checks are disabled **only for these ephemeral local proxies**;
Infisical handles upstream authentication. Use a trusted controller.

Enable `unparsed_is_failed = True` and `any_unparsed_is_failed = True` in
Ansible's `[inventory]` configuration to fail the run when context or account
resolution fails. Your project's playbooks, roles, `group_vars`, and `host_vars`
use normal Ansible behavior. Inventories must end in `.infisical.yml` or
`.infisical.yaml`. No credentials belong in this collection or its inventory.
