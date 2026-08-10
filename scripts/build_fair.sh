#!/bin/bash
# Build the Fair-Parke (FP) Fortran program from the vendored source.
#
# The vendored FMFP/EngineFM/fp.for is NEVER edited. A copy is made into
# build/fair/ and two mechanical fixes are applied there:
#   1. ACCESS='TRANSPARENT' (a legacy non-standard extension, used only by
#      dead multicountry code paths) -> ACCESS='STREAM' so gfortran accepts it.
#   2. GETCL (platform-specific command-line intrinsic) is satisfied by the
#      stub in scripts/getcl_stub.f, which forces stdin-driven operation.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GFORTRAN="${GFORTRAN:-$REPO_ROOT/.mamba/envs/toolchain/bin/gfortran}"
SRC="$REPO_ROOT/FMFP/EngineFM/fp.for"
BUILD_DIR="$REPO_ROOT/build/fair"
OUT_DIR="$REPO_ROOT/data/artifacts/fair/bin"
OUT="$OUT_DIR/fp"

if [ ! -x "$GFORTRAN" ]; then
    echo "ERROR: gfortran not found at $GFORTRAN — run scripts/bootstrap.sh first" >&2
    exit 1
fi

# conda-forge gfortran on macOS drives clang for assembly/linking; make sure
# the env's own tools (and the system fallback) are on PATH.
export PATH="$(dirname "$GFORTRAN"):$PATH:/usr/bin"
# conda-forge gfortran's macOS driver specs fail ("too many arguments to
# %:version-compare") when the deployment target is unset.
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-$(sw_vers -productVersion | cut -d. -f1-2)}"

mkdir -p "$BUILD_DIR" "$OUT_DIR"
cp "$SRC" "$BUILD_DIR/fp.for"

echo "==> Applying mechanical gfortran compatibility patches"
python3 - "$BUILD_DIR/fp.for" << 'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()

# Fix 1: ACCESS='TRANSPARENT' (legacy extension, dead multicountry paths)
# -> ACCESS='STREAM' so gfortran accepts it. 7 occurrences expected.
n = src.count("'TRANSPARENT'")
assert n == 7, f"expected 7 TRANSPARENT occurrences, found {n}"
src = src.replace("'TRANSPARENT'", "'STREAM'")

# Fix 2: RAN3 is implicitly REAL(4) but its call sites under IMPLICIT
# REAL*8 expect REAL(8); historic compilers resolved this at link time,
# gfortran rejects it. Declare the function REAL*8 (RAN3 feeds only
# stochastic-simulation paths, unused by deterministic solves) and add a
# matching declaration in RNORA, the one default-REAL caller.
old = "      FUNCTION RAN3(IDUM)\n"
assert src.count(old) == 1
src = src.replace(old, "      REAL*8 FUNCTION RAN3(IDUM)\n")

old = "      FUNCTION RNORA(IDUM)\n"
assert src.count(old) == 1
src = src.replace(old, "      FUNCTION RNORA(IDUM)\n      REAL*8 RAN3\n")

open(path, "w").write(src)
print("    patches applied")
PYEOF

FFLAGS=(-std=legacy -ffixed-line-length-80 -fno-automatic -finit-local-zero
        -fno-range-check -fdollar-ok -O2)

# conda-forge gfortran 16's macOS link specs are broken ("too many arguments
# to %:version-compare"), so compile with gfortran and link with the system
# clang against the env's libgfortran.
echo "==> Compiling with $("$GFORTRAN" --version | head -1)"
"$GFORTRAN" "${FFLAGS[@]}" -c -o "$BUILD_DIR/fp.o" "$BUILD_DIR/fp.for" \
    2> "$BUILD_DIR/compile.log" || {
        echo "ERROR: compile failed; last 50 lines of $BUILD_DIR/compile.log:" >&2
        tail -50 "$BUILD_DIR/compile.log" >&2
        exit 1
    }
"$GFORTRAN" "${FFLAGS[@]}" -c -o "$BUILD_DIR/getcl_stub.o" "$REPO_ROOT/scripts/getcl_stub.f" \
    2>> "$BUILD_DIR/compile.log"

ENV_LIB="$(dirname "$(dirname "$GFORTRAN")")/lib"
echo "==> Linking with system clang (libgfortran from $ENV_LIB)"
/usr/bin/clang "$BUILD_DIR/fp.o" "$BUILD_DIR/getcl_stub.o" -o "$OUT" \
    -L"$ENV_LIB" -Wl,-rpath,"$ENV_LIB" -lgfortran \
    2> "$BUILD_DIR/link.log" || {
        echo "ERROR: link failed:" >&2
        cat "$BUILD_DIR/link.log" >&2
        exit 1
    }

echo "==> Compiled: $OUT"
grep -ci "warning" "$BUILD_DIR/compile.log" | xargs -I{} echo "    ({} warning lines in compile.log)"

# Smoke test: fp should start, read QUIT from stdin, and exit cleanly.
SMOKE_DIR="$(mktemp -d)"
( cd "$SMOKE_DIR" && printf 'QUIT ;\n' | "$OUT" > smoke.log 2>&1 ) || {
    echo "ERROR: smoke test failed; output:" >&2
    cat "$SMOKE_DIR/smoke.log" >&2
    exit 1
}
echo "==> Smoke test (QUIT) passed"
rm -rf "$SMOKE_DIR"
