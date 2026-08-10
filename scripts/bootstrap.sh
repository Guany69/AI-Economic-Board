#!/bin/bash
# Bootstrap the local toolchain (no sudo, no Homebrew, no Docker):
#   1. micromamba into <repo>/.mamba
#   2. conda-forge env "toolchain" with gfortran + postgresql
#   3. pip install -e ".[dev]"
#   4. import verifications
#
# Idempotent: safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAMBA_ROOT="$REPO_ROOT/.mamba"
MAMBA_BIN="$MAMBA_ROOT/bin/micromamba"
ENV_NAME="toolchain"
ENV_PREFIX="$MAMBA_ROOT/envs/$ENV_NAME"

echo "==> Repo: $REPO_ROOT"

# --- 1. micromamba ---------------------------------------------------------
if [ ! -x "$MAMBA_BIN" ]; then
    echo "==> Installing micromamba into $MAMBA_ROOT"
    mkdir -p "$MAMBA_ROOT/bin"
    ARCH="$(uname -m)"
    OS="$(uname -s)"
    if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
        PLATFORM="osx-arm64"
    elif [ "$OS" = "Darwin" ]; then
        PLATFORM="osx-64"
    else
        PLATFORM="linux-64"
    fi
    curl -Ls "https://micro.mamba.pm/api/micromamba/$PLATFORM/latest" \
        | tar -xj -C "$MAMBA_ROOT" bin/micromamba
else
    echo "==> micromamba already present"
fi
export MAMBA_ROOT_PREFIX="$MAMBA_ROOT"

# --- 2. toolchain env: gfortran + postgresql --------------------------------
if [ ! -d "$ENV_PREFIX" ]; then
    echo "==> Creating env '$ENV_NAME' (gfortran + postgresql from conda-forge)"
    "$MAMBA_BIN" create -y -n "$ENV_NAME" -c conda-forge gfortran postgresql
else
    echo "==> Env '$ENV_NAME' already exists"
fi

GFORTRAN="$ENV_PREFIX/bin/gfortran"
INITDB="$ENV_PREFIX/bin/initdb"
"$GFORTRAN" --version | head -1
"$INITDB" --version

# --- 3. python deps ----------------------------------------------------------
echo "==> pip install -e \".[dev]\""
python3 -m pip install -e "$REPO_ROOT[dev]" --quiet

# --- 4. verifications ----------------------------------------------------------
echo "==> Verifying python imports"
python3 - << 'EOF'
import importlib
for mod in ("fastapi", "sqlalchemy", "alembic", "psycopg", "anthropic",
            "yaml", "pydantic_settings", "taxcalc"):
    importlib.import_module(mod)
    print(f"  ok: {mod}")
EOF

echo "==> Bootstrap complete."
echo "    gfortran: $GFORTRAN"
echo "    postgres bin dir: $ENV_PREFIX/bin"
echo "    Next: scripts/build_fair.sh"
