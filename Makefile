PYTHON ?= python3

.PHONY: setup tools test deploy inspect check act package

setup:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt

tools:
	.venv/bin/python scripts/install_tools.py

test:
	.venv/bin/python -m unittest discover -s tests -v

deploy:
	.venv/bin/python scripts/deploy.py $(ARGS)

inspect:
	.venv/bin/python scripts/deploy.py --inventory-only

check:
	.venv/bin/python scripts/deploy.py --check --diff

act:
	.venv/bin/python scripts/run_act.py $(ARGS)

package:
	mkdir -p dist
	.venv/bin/ansible-galaxy collection build plugin/ansible_collections/poc/infisical_pam --output-path dist --force
