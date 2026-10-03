"""Parse the Markdown emitted by Infisical CLI 0.43.132 RenderInstructions.

Upstream: packages/pam/agent/instructions.go. This is a format adapter, not
a general Markdown parser; unknown/missing SSH connection data fails closed.
"""

from dataclasses import dataclass
import re


class ContextError(ValueError):
    """The PAM context cannot safely resolve the requested account."""


@dataclass(frozen=True)
class Endpoint:
    account: str
    kind: str
    host: str
    port: int
    needs_approval: bool


def normalize_account(value):
    if not isinstance(value, str) or not value.strip():
        raise ContextError("PAM account must be a nonempty path")
    account = value.strip().strip("/")
    if not account or any(part in ("", ".", "..") for part in account.split("/")):
        raise ContextError("PAM account must be a valid folder/account path")
    if any(ord(char) < 32 for char in account):
        raise ContextError("PAM account contains a control character")
    return account


def parse_context(document):
    endpoints = {}
    sections = re.split(r"^##\s+", document, flags=re.MULTILINE)[1:]
    for section in sections:
        heading, _, body = section.partition("\n")
        match = re.fullmatch(r"(.+) \(([^()]+)\)\s*", heading)
        if not match:
            continue  # e.g. the trailing Rules section
        account = normalize_account(match[1])
        kind = match[2]
        if kind != "SSH":
            continue
        if account in endpoints:
            raise ContextError(f"Duplicate SSH PAM account: {account}")
        addresses = re.findall(r"^- Host:\s*([^,\s]+),\s*port\s+(\d+)\s*$", body, re.MULTILINE)
        if len(addresses) != 1:
            raise ContextError(f"Expected one Host/port entry for {account}; unsupported PAM context format")
        host, port_text = addresses[0]
        port = int(port_text)
        if host != "127.0.0.1" or not 1 <= port <= 65535:
            raise ContextError(f"Invalid local SSH proxy endpoint for {account}")
        endpoints[account] = Endpoint(account, kind, host, port, "STATUS: NEEDS APPROVAL" in body)
    return endpoints


def resolve_account(endpoints, account):
    account = normalize_account(account)
    if account not in endpoints:
        raise ContextError(f"SSH account {account!r} is missing from PAM context; pass --account {account}")
    endpoint = endpoints[account]
    if endpoint.needs_approval:
        raise ContextError(f"PAM account {account!r} needs approval; approve access and start a new run")
    return endpoint

