#!/usr/bin/env python3
"""Run the real workflow with act's native host executor (no Docker needed)."""

import os
import shutil
import sys

from settings import ROOT, load_settings


def main():
    os.chdir(ROOT)
    load_settings()
    act = shutil.which("act")
    if not act:
        raise SystemExit("Run make tools to install the pinned local act binary")
    # Native act still executes shell steps with --dryrun. Explicitly gate
    # deployment, and do not let this launcher's make ARGS reach nested make.
    os.environ.pop("MAKEFLAGS", None)
    os.environ.pop("MFLAGS", None)
    # act reads the values from the environment, masks them, and supplies them as
    # workflow secrets. Secret values never appear in process arguments.
    command = [act, "workflow_dispatch", "--workflows", ".github/workflows/deploy.yml",
               "--eventpath", ".github/act-event.json",
               "--job", "local-deploy", "--platform", "ubuntu-latest=-self-hosted",
               "--env-file", "/dev/null", "--no-cache-server",
               "--env", f"LOCAL_WORKSPACE={ROOT}",
               "--env", f"PAM_INVENTORY={os.environ.get('PAM_INVENTORY', 'example/inventory.infisical.yml')}",
               "--env", f"PAM_PLAYBOOK={os.environ.get('PAM_PLAYBOOK', 'example/nginx.yml')}",
               "--env", f"LOCAL_DRY_RUN={'true' if '--dryrun' in sys.argv[1:] or '-n' in sys.argv[1:] else 'false'}",
               "--var", f"INFISICAL_DOMAIN={os.environ['INFISICAL_DOMAIN']}",
               "--secret", "INFISICAL_UNIVERSAL_AUTH_CLIENT_ID",
               "--secret", "INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET", *sys.argv[1:]]
    # Keep act's cache and native runner state local to this demo.
    os.environ["XDG_CACHE_HOME"] = str(ROOT / ".cache")
    os.execv(act, command)


if __name__ == "__main__":
    main()
