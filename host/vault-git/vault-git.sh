#!/bin/bash
# Commits the Markdown vault (~/vault) to a local git repo, so every change can be undone.
set -euo pipefail
cd "${VAULT_DIR:-$HOME/vault}"
[ -d .git ] || { git init -q; git config user.name "vault autosave"; git config user.email "vault@localhost"; }
git add -A
git diff --cached --quiet || git commit -q -m "autosave $(date -Is)"
