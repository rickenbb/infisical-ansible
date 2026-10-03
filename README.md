# Infisical PAM + Ansible

## A. Problem and solution

Ansible needs SSH access to private hosts. Infisical PAM opens temporary local
proxies and supplies the target credentials through its gateway:

```text
Laptop / GitHub runner → localhost proxy → Infisical Gateway → nfitest → nginx
```

The standalone [inventory plugin](plugin/ansible_collections/poc/infisical_pam)
maps account names to ports in `INFISICAL_PAM_CONTEXT_FILE`. The normal
[nginx playbook](example/nginx.yml) installs nginx, starts it, and checks HTTP
on `ssh/infitest` (`root@192.168.61.173`, certificate authentication).

This unofficial PoC uses CLI **0.43.132**, Ansible **2.19.9**, and Infisical's
[Markdown context format](https://github.com/Infisical/cli/blob/v0.43.132/packages/pam/agent/instructions.go).
Format changes may require a parser update. Only loopback SSH endpoints are
accepted; their ephemeral host keys are not checked. Use a trusted controller.

## B. Use the plugin

**Run this example** (Python 3.11+, OpenSSH, macOS or Linux):

```sh
make setup PYTHON=python3.12
make tools                       # pinned binaries under .tools/, no global install
cp .env.example .env              # only if you do not already have .env
# Fill CLIENT_ID, CLIENT_SECRET, INFISICAL_URL in .env.
make inspect                     # resolve PAM inventory, no target changes
make deploy                      # install nginx and verify HTTP 200
make act                         # run deploy.yml locally using act
```

The identity needs PAM project membership and access to `ssh/infitest`.
The target needs Python 3 and a package manager. Adjust the account and expected
IP in [the inventory](example/inventory.infisical.yml) for another host; non-root
accounts need sudo and `ansible_become: true`. `.env` stays out of Git.

`make act` runs the deployment workflow's `local-deploy` job on your machine with
`.env` credentials. The separate local job avoids act downloading remote actions
even when their steps are skipped. It deploys to the real target; Docker is unnecessary.
Use `make act ARGS=--dryrun` to validate the workflow without deploying.
[act cannot issue GitHub OIDC tokens](https://nektosact.com/not_supported.html).

**On GitHub:** configure the machine identity's [GitHub OIDC auth](https://infisical.com/docs/documentation/platform/identities/oidc-auth/github).
Set repository/environment variables `INFISICAL_DOMAIN`,
`INFISICAL_MACHINE_IDENTITY_ID` and `INFISICAL_OIDC_AUDIENCE` (default `infisical`).
Bind it to your repository, workflow, and `demo` environment, then manually run
**Deploy nginx through Infisical PAM**. GitHub uses OIDC without a client secret.
The workflow installs bubblewrap for Infisical's Linux sandbox.

Validation: all eight offline tests pass through the local act job. Direct
deployment has been confirmed working; the updated act job has been verified
with deployment explicitly skipped using `ARGS=--dryrun`.

**Reuse independently:** copy `plugin/ansible_collections/poc` into your Ansible
collections directory, or build/install the collection:

```sh
make package
ansible-galaxy collection install dist/poc-infisical_pam-0.1.0.tar.gz
```

Create an inventory whose filename ends in `.infisical.yml`:

```yaml
plugin: poc.infisical_pam.inventory
hosts:
  web01:
    account: servers/web01
    groups: [web]
    vars:
      ansible_become: true
```

With CLI login or standard Infisical authentication environment variables set:

```sh
infisical pam agentic access --account servers/web01 --reason deploy -- \
  ansible-playbook -i inventory.infisical.yml site.yml
```

Repeat `--account` for each host. Per-host `groups`/`vars` and top-level `vars`
are supported. Enable `[inventory] unparsed_is_failed = True` in your own
`ansible.cfg` to fail on missing context. `make test` runs the offline checks.
