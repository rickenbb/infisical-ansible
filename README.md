# Infisical PAM + Ansible

Run ordinary Ansible playbooks through temporary Infisical PAM SSH proxies.
The gateway supplies the target's credentials; inventories contain PAM account
names rather than target passwords or keys.

```text
Ansible controller → localhost PAM proxy → Infisical Gateway → target
```

The repository provides a standard Ansible collection,
[`poc.infisical_pam`](plugin/ansible_collections/poc/infisical_pam), a general
controller launcher, and a reusable GitHub workflow. The collection reads
the live `INFISICAL_PAM_CONTEXT_FILE` and supplies the SSH connection adapter;
it does not authenticate or start proxies. The launcher requests the unique
accounts declared in an inventory and runs Ansible inside that PAM session.

This unofficial integration is tested with Infisical CLI **0.43.132** and
Ansible **2.19.9**. The context parser depends on Infisical's
[Markdown format](https://github.com/Infisical/cli/blob/v0.43.132/packages/pam/agent/instructions.go).
Only loopback SSH proxies are accepted. SSH host-key checks are disabled for
these ephemeral proxies; Infisical handles upstream authentication.

## Use from another GitHub repository

Copy the files in [example/reuse](example/reuse) into your repository:

- `deploy.yml` → `.github/workflows/deploy.yml`
- `inventory.infisical.yml` → your project root
- `site.yml` → your project root, or use an existing playbook

Change the inventory's `account` to an account your machine identity can access.
The identity needs PAM project membership and account access. Adjust inventory
groups and host variables to match your playbook; a non-root account can use
`ansible_become: true` if it has sudo access. The target needs Python 3.

The inventory selects `poc.infisical_pam.ssh`, which uses Ansible's standard
OpenSSH connection options. The pinned Infisical gateway
[forwards normal SSH channel data without forwarding stderr](https://github.com/Infisical/cli/blob/v0.43.132/packages/pam/handlers/ssh/proxy.go).
The adapter redirects task stderr into stdout on the target so Ansible can
receive sudo's password prompt and report remote errors. Supply
`ansible_become_password` through your normal secret mechanism when sudo
requires a password. Module pipelining stays enabled, and file-transfer streams
retain their binary contents. Targets need a POSIX shell; task diagnostics
appear in stdout.

Set the Actions variable `INFISICAL_DOMAIN` to your instance URL. Add these
Actions **secrets** at repository level or in your chosen deployment environment:

- `INFISICAL_UNIVERSAL_AUTH_CLIENT_ID`
- `INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET`

Your caller workflow can be as small as:

```yaml
name: Deploy
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  deploy:
    uses: rickenbb/infisical-ansible/.github/workflows/ansible-pam.yml@main
    with:
      inventory: inventory.infisical.yml
      playbook: site.yml
      infisical-domain: ${{ vars.INFISICAL_DOMAIN }}
      environment: production
    secrets:
      INFISICAL_UNIVERSAL_AUTH_CLIENT_ID: ${{ secrets.INFISICAL_UNIVERSAL_AUTH_CLIENT_ID }}
      INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET: ${{ secrets.INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET }}
```

Push the toolkit changes before using this caller. Replace `@main` with a tested
release tag or commit SHA for reproducible deployments. No Galaxy publication
is required. The reusable workflow installs the collection from the **same
commit that defines the workflow**, using GitHub.com's
[`job.workflow_repository` and `job.workflow_sha` contexts](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#job-context).
The workflow checks out the calling repository for its playbooks and a separate
`.ansible-pam/` checkout for the controller tools. GitHub Enterprise Server does
not currently provide these workflow identity contexts; use the collection and
CLI directly there.

If this toolkit repository is private, enable reusable-workflow access for the
calling repositories and pass the optional `PAM_TOOLKIT_TOKEN` secret with read
access to the toolkit so the second checkout can succeed.

### Workflow inputs

| Input | Purpose | Default |
| --- | --- | --- |
| `inventory` | PAM inventory filename, relative to the project directory | Required |
| `playbook` | Playbook filename, relative to the project directory | Required |
| `infisical-domain` | Infisical instance URL | Required |
| `working-directory` | Project directory within the calling repository | `.` |
| `environment` | GitHub deployment environment in the calling repository | `deployment` |
| `ansible-args` | JSON array of additional Ansible arguments | `[]` |
| `collections-requirements` | Optional collection requirements file, relative to the project | Empty |
| `python-requirements` | Optional pip requirements file, relative to the project | Empty |
| `reason` | PAM audit reason | Calling repository and commit |
| `validate-only` | Install and validate without requesting PAM access | `false` |

For example, `ansible-args: '["--check", "--diff", "--limit", "web01"]'`
passes arguments without shell evaluation. `--check` still opens PAM access;
`validate-only: true` does not. The launcher requests all accounts declared in
the inventory, even when Ansible uses `--limit`.

The workflow installs its own PAM collection; `collections-requirements` is for
additional dependencies your playbooks use. Your project's `ansible.cfg`,
`group_vars`, `host_vars`, roles, and playbooks remain in the calling repository.
The installed collection directory is supplied through `ANSIBLE_COLLECTIONS_PATH`.

Authentication uses Universal Auth, matching the local example. The workflow
runs on Ubuntu 24.04, configures bubblewrap's AppArmor user-namespace permission,
and verifies sandbox startup before requesting access. The runner must be able
to reach your Infisical instance and PAM gateway.

## Use the collection with any Ansible controller

Ansible supports installation from Git, built artifacts, Galaxy, and private
Automation Hub. See [Ansible's installation guide](https://docs.ansible.com/projects/ansible/latest/collections_guide/collections_installing.html).
For Git installation, put this in `collections/requirements.yml` and replace
`main` with a tested tag or SHA:

```yaml
collections:
  - name: https://github.com/rickenbb/infisical-ansible.git#/plugin/ansible_collections/poc/infisical_pam/
    type: git
    version: main
```

```sh
ansible-galaxy collection install -r collections/requirements.yml
```

Create an inventory whose filename ends in `.infisical.yml` or `.infisical.yaml`:

```yaml
plugin: poc.infisical_pam.inventory
hosts:
  web01:
    account: servers/web01
    groups: [web]
```

With the pinned Infisical CLI installed and standard `INFISICAL_*`
authentication environment variables set, run your normal playbook:

```sh
infisical pam agentic access --agent generic --account servers/web01 --reason deploy -- \
  ansible-playbook -i inventory.infisical.yml site.yml
```

Repeat `--account` for each distinct PAM account. The plugin supports per-host
`groups`/`vars` and top-level `vars`. Enable strict inventory parsing in your
controller's `ansible.cfg`:

```ini
[inventory]
unparsed_is_failed = True
any_unparsed_is_failed = True
```

To derive accounts automatically, use the launcher from a toolkit checkout:

```sh
/path/to/infisical-ansible/.venv/bin/python /path/to/infisical-ansible/scripts/deploy.py \
  --project-dir /path/to/your-project \
  --inventory inventory.infisical.yml --playbook site.yml -- --check --diff
```

Run `make setup tools` in the toolkit checkout first, and install the collection
into the controller's normal Ansible collection path. The launcher reads `.env`
from the project directory without overriding existing environment variables.
It preserves `ANSIBLE_CONFIG`, uses normal collection discovery, and supports
`--inventory-only`, `--validate-only`, and `--args-json`.

Build an installable collection artifact with `make package` and install it using
`ansible-galaxy collection install dist/poc-infisical_pam-0.1.0.tar.gz`.
The existing namespace is retained for compatibility. Choose a namespace you own
before publishing to Galaxy; update consumers if you rename it.

## Run the nginx example locally

Python 3.11+, OpenSSH, macOS or Linux:

```sh
make setup PYTHON=python3.12
make tools
cp .env.example .env              # only if you do not already have .env
# Fill CLIENT_ID, CLIENT_SECRET and INFISICAL_URL in .env.
make inspect
make deploy
make act ARGS=--dryrun            # run tests and validate inputs without access
make act                         # deploy to the real example target
```

The example installs nginx on `ssh/infitest` and verifies HTTP 200. Select a
different inventory and playbook with:

```sh
make deploy PAM_INVENTORY=inventories/production.infisical.yml PAM_PLAYBOOK=site.yml
make check PAM_INVENTORY=inventories/production.infisical.yml PAM_PLAYBOOK=site.yml
```

`ARGS` passes extra Ansible flags to `deploy`, `check`, and `inspect`, or act flags
to `act`. `make act` uses the native host executor without Docker. A dedicated
local job avoids act downloading remote actions for skipped setup steps.

The manual nginx workflow now calls the same reusable workflow as other
repositories, with the existing `demo` environment. Its fallback instance URL
is specific to this example. The general launcher defaults to Infisical US
Cloud when no domain is configured.

## Development

`make test` runs offline parser, launcher, and real Ansible integration checks,
including sudo password negotiation and binary file transfers through a local
transport fixture that drops stderr like the pinned gateway.
The launcher tests install the collection in an isolated project and verify
that project's own Ansible configuration. CI also installs the built artifact
and exercises the reusable workflow in `validate-only` mode without PAM secrets.
Live access always requires an active Infisical session and authorized accounts.
