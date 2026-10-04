"""Inherit SSH options from the installed ansible-core version."""

import yaml

from ansible.plugins.connection.ssh import DOCUMENTATION as SSH_DOCUMENTATION


class ModuleDocFragment:
    DOCUMENTATION = yaml.safe_dump({"options": yaml.safe_load(SSH_DOCUMENTATION)["options"]})
