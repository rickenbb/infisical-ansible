# Infisical PAM inventory (unofficial PoC)

Use `poc.infisical_pam.inventory` inside `infisical pam agentic access`.
The collection needs only Ansible and the context file supplied by Infisical;
it does not authenticate, start proxies, or depend on the demo scripts.

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
`plugins/module_utils/context.py` is the only code coupled to Infisical's
Markdown format (CLI 0.43.132). Only loopback SSH endpoints are accepted.
SSH host-key checks are disabled **only for these ephemeral local proxies**;
Infisical handles upstream authentication. Use a trusted controller.

