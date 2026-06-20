#!/usr/bin/env bash
# Run the Yard test suite.
#
#   ./tests/run.sh
#   KUJO=/path/to/kujo/target/release/kujo ./tests/run.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KUJO="${KUJO:-kujo}"

cd "$PROJECT_DIR"
exec "$KUJO" run "$PROJECT_DIR/tests/yard_test.kujo"
