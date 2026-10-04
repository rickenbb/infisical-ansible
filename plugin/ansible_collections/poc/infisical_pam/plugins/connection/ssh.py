"""Keep remote diagnostics and become prompts visible through PAM gateways."""

from ansible.plugins.connection.ssh import Connection as SSHConnection

DOCUMENTATION = r'''
name: ssh
short_description: Run SSH commands through Infisical PAM proxies
description:
  - Uses Ansible's built-in SSH connection and its standard options.
  - Redirects task stderr into stdout before it reaches the PAM gateway.
  - Infisical CLI 0.43.132's gateway forwards normal SSH channel data but does
    not forward extended channel data, including stderr and sudo prompts.
  - Requires a POSIX shell on the target. Task diagnostics appear in stdout.
  - File-transfer streams are left untouched to preserve binary contents.
author: infisical-ansible contributors
extends_documentation_fragment:
  - ansible.builtin.connection_pipelining
  - poc.infisical_pam.ssh
'''


class Connection(SSHConnection):
    def exec_command(self, cmd, in_data=None, sudoable=True):
        # Apply the redirect around the whole command, including sudo itself.
        # Keep stdin, module pipelining, and the remote exit status unchanged.
        # Newlines also keep a trailing shell comment from swallowing ')'.
        # Ansible uses sudoable=False for piped file transfers. Merging dd's
        # stderr there would append its transfer statistics to downloaded files.
        if sudoable:
            cmd = f"(\n{cmd}\n) 2>&1"
        return super().exec_command(cmd, in_data=in_data, sudoable=sudoable)
