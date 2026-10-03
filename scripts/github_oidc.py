#!/usr/bin/env python3
"""Fetch a GitHub OIDC JWT for the CLI; never write it to console or argv."""

import json
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


def main():
    if os.environ.get("ACT") == "true":
        raise SystemExit("act cannot issue GitHub OIDC tokens; use local machine identity credentials")
    required = ("ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_ID_TOKEN_REQUEST_TOKEN", "INFISICAL_MACHINE_IDENTITY_ID")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Set INFISICAL_MACHINE_IDENTITY_ID and grant the workflow id-token: write")
    url = urlsplit(os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"])
    query = dict(parse_qsl(url.query))
    query["audience"] = os.environ.get("INFISICAL_OIDC_AUDIENCE", "infisical")
    request = Request(urlunsplit(url._replace(query=urlencode(query))), headers={
        "Authorization": f"Bearer {os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}"
    })
    with urlopen(request, timeout=30) as response:
        jwt = json.load(response)["value"]
    if not isinstance(jwt, str) or "\n" in jwt or "\r" in jwt or not jwt:
        raise SystemExit("GitHub returned an invalid OIDC token")
    print(f"::add-mask::{jwt}")
    with open(os.environ["GITHUB_ENV"], "a") as environment:
        environment.write(f"INFISICAL_AUTH_METHOD=oidc-auth\nINFISICAL_JWT={jwt}\n")


if __name__ == "__main__":
    main()

