"""Controller settings; the reusable collection never reads .env files."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def load_settings(project_dir=ROOT):
    load_dotenv(Path(project_dir) / ".env", override=False, interpolate=False)
    for local, standard in {
        "CLIENT_ID": "INFISICAL_UNIVERSAL_AUTH_CLIENT_ID",
        "CLIENT_SECRET": "INFISICAL_UNIVERSAL_AUTH_CLIENT_SECRET",
        "INFISICAL_URL": "INFISICAL_DOMAIN",
    }.items():
        value = os.environ.pop(local, "")
        if value and not os.environ.get(standard):
            os.environ[standard] = value
    if not os.environ.get("INFISICAL_AUTH_METHOD") and os.environ.get("INFISICAL_UNIVERSAL_AUTH_CLIENT_ID"):
        os.environ["INFISICAL_AUTH_METHOD"] = "universal-auth"
    os.environ.setdefault("INFISICAL_DOMAIN", "https://app.infisical.com/api")
    os.environ["PATH"] = os.pathsep.join([str(ROOT / ".tools/bin"), str(ROOT / ".venv/bin"), os.environ["PATH"]])
