#!/usr/bin/env bash
# Run the Yard test suite.
#
#   ./tests/run.sh
#   RUFF=/path/to/ruff/target/release/ruff ./tests/run.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUFF="${RUFF:-ruff}"

cd "$PROJECT_DIR"
exec "$RUFF" run "$PROJECT_DIR/tests/yard_test.ruff"
