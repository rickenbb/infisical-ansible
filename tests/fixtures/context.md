# Infisical PAM: live privileged access

## ssh/infitest (SSH)
- Host: 127.0.0.1, port 52431
- Connection string: ssh pam@127.0.0.1 -p 52431

## production/second (SSH)
- Host: 127.0.0.1, port 52432

## production/database (PostgreSQL)
- Host: 127.0.0.1, port 52433

## production/pending (SSH)
- STATUS: NEEDS APPROVAL. This account needs a human to approve access, and is not usable
  yet.
- Host: 127.0.0.1, port 52434

## Rules
- These proxies stop working when the Infisical session ends.
