PYTHON ?= python3
PAM_INVENTORY ?= example/inventory.infisical.yml
PAM_PLAYBOOK ?= example/nginx.yml

.PHONY: setup tools test deploy inspect check act package

setup:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt

tools:
	.venv/bin/python scripts/install_tools.py $(ARGS)

test:
	.venv/bin/python -m unittest discover -s tests -v

deploy:
	.venv/bin/python scripts/deploy.py --inventory "$(PAM_INVENTORY)" --playbook "$(PAM_PLAYBOOK)" $(ARGS)

inspect:
	.venv/bin/python scripts/deploy.py --inventory "$(PAM_INVENTORY)" --inventory-only $(ARGS)

check:
	.venv/bin/python scripts/deploy.py --inventory "$(PAM_INVENTORY)" --playbook "$(PAM_PLAYBOOK)" --check --diff $(ARGS)

act:
	PAM_INVENTORY="$(PAM_INVENTORY)" PAM_PLAYBOOK="$(PAM_PLAYBOOK)" .venv/bin/python scripts/run_act.py $(ARGS)

package:
	mkdir -p dist
	.venv/bin/ansible-galaxy collection build plugin/ansible_collections/poc/infisical_pam --output-path dist --force
