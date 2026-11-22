#!/usr/bin/env bash
# Exercise process control and the actual HTTP routes with isolated state.
set -euo pipefail

project="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
yard="$project/bin/yard"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/yard-integration.XXXXXX")"
dashboard=
children=()
cleanup() {
  local pid
  if [[ -f "$scratch/pids" ]]; then
    while IFS= read -r pid; do
      if [[ "$(ps -o command= -p "$pid" 2>/dev/null)" == 'sleep 45' ]]; then
        kill -KILL "$pid" 2>/dev/null || true
      fi
    done < "$scratch/pids"
  fi
  for pid in "${dashboard:-}" "${children[@]}"; do
    if [[ -n "$pid" ]]; then
      kill -KILL "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  rm -rf "$scratch"
}
trap cleanup EXIT

fail() { printf 'Integration failure: %s\n' "$*" >&2; exit 1; }
trap 'fail "line $LINENO"' ERR
expect_error() {
  local expected="$1"
  shift
  if "$@" >"$scratch/receipt" 2>&1; then
    fail "unexpected success: $*"
  fi
  if ! grep -qF "$expected" "$scratch/receipt"; then
    cat "$scratch/receipt" >&2
    fail "expected '$expected' from $*"
  fi
}

export YARD_CONFIG="$scratch/config.json" YARD_DIR="$scratch/state"
export YARD_TEST_LISTENERS="$scratch/listeners"
export YARD_TEST_SCAN_ERROR="$scratch/scan-error"
mkdir "$scratch/mock" "$scratch/service's cwd"
cd "$scratch"
export PATH="$scratch/mock:$PATH"
cat > "$scratch/mock/lsof" <<'MOCK'
#!/bin/sh
if [ -f "$YARD_TEST_SCAN_ERROR" ]; then
    echo 'fixture scan error' >&2
    exit 1
fi
if [ ! -s "$YARD_TEST_LISTENERS" ]; then
    exit 1
fi
cat "$YARD_TEST_LISTENERS"
MOCK
chmod +x "$scratch/mock/lsof"

# The short-lived fixture is disposable and records its PID for cleanup.
cat > "$scratch/process" <<'FIXTURE'
#!/bin/sh
printf '%s\n' "$$" >> "$1"
printf 'started in %s\n' "$PWD"
if [ "${2-}" = stubborn ]; then
    trap '' TERM
    exec sleep 45
fi
exec sleep 45
FIXTURE
chmod +x "$scratch/process"
export PATH="$scratch:$PATH"
cat > "$YARD_CONFIG" <<'JSON'
{"services":[
  {"id":"worker","port":25081,"cwd":"service's cwd","group":"constructor","start":"process ../pids"},
  {"id":"other","port":25082,"start":"process pids"},
  {"id":"stubborn","port":25083,"start":"process pids stubborn"},
  {"id":"protected","port":25084,"sensitive":true}
]}
JSON

# Duplicate starts serialize; unrelated starts preserve both state entries.
"$yard" start worker >"$scratch/start-one" &
first=$!
"$yard" start worker >"$scratch/start-two" &
second=$!
"$yard" start other >/dev/null &
third=$!
successes=0
if wait "$first"; then successes=$((successes + 1)); fi
if wait "$second"; then successes=$((successes + 1)); fi
wait "$third"
[[ "$successes" == 1 ]] || fail "duplicate starts did not serialize"
grep -q '"worker"' "$YARD_DIR/managed.json"
grep -q '"other"' "$YARD_DIR/managed.json"
grep -q "started in .*service's cwd" "$YARD_DIR/logs/worker.log"

"$yard" restart worker >/dev/null
grep -q '"restart_count": 1' "$YARD_DIR/managed.json"
"$yard" stop worker >/dev/null
"$yard" stop worker >/dev/null

# A corrupt state file remains intact and blocks changes.
cp "$YARD_DIR/managed.json" "$scratch/saved-state"
printf '{wrong' >"$YARD_DIR/managed.json"
expect_error "could not start" "$yard" start worker
[[ "$(cat "$YARD_DIR/managed.json")" == '{wrong' ]] || fail "corrupt state was overwritten"
cp "$scratch/saved-state" "$YARD_DIR/managed.json"

"$yard" stop other >/dev/null

# A process that ignores TERM is never replaced by restart.
"$yard" start stubborn >/dev/null
expect_error "still running after SIGTERM" "$yard" restart stubborn
"$yard" stop stubborn --force --yes >/dev/null

# Legacy records and reused PIDs never authorize signaling a non-listener.
sleep 45 &
disposable=$!
children+=("$disposable")
printf '{"worker":{"pid":%s}}\n' "$disposable" >"$YARD_DIR/managed.json"
expect_error "cannot verify legacy tracked pid" "$yard" stop worker
printf '{"worker":{"pid":%s,"process_started":"old process"}}\n' "$disposable" >"$YARD_DIR/managed.json"
"$yard" stop worker >/dev/null
kill -0 "$disposable" || fail "a mismatched tracked PID was signaled"
touch "$YARD_TEST_SCAN_ERROR"
expect_error "listener scan failed" "$yard" stop-port 25081
expect_error '"scan_error"' "$yard" scan --no-health --json
rm "$YARD_TEST_SCAN_ERROR"
printf 'unexpected lsof output\n' >"$YARD_TEST_LISTENERS"
expect_error "listener scan incomplete" "$yard" stop-port 25081
rm "$YARD_TEST_LISTENERS"
expect_error "unknown option" "$yard" stop worker --forces

# A PID owning a sensitive port also requires confirmation through its other
# ports. Two distinct listeners on one configured port are ambiguous.
printf 'fixture %s dev 3u IPv4 0x1 0t0 TCP *:25081 (LISTEN)\n' "$disposable" >"$YARD_TEST_LISTENERS"
printf 'fixture %s dev 4u IPv4 0x1 0t0 TCP *:25084 (LISTEN)\n' "$disposable" >>"$YARD_TEST_LISTENERS"
expect_error "sensitive service" "$yard" stop worker
expect_error "sensitive service" "$yard" stop-port 25081
kill -0 "$disposable" || fail "sensitive listener was signaled without confirmation"
sleep 45 &
second_listener=$!
children+=("$second_listener")
printf 'fixture %s dev 3u IPv4 0x1 0t0 TCP 127.0.0.2:25081 (LISTEN)\n' "$second_listener" >>"$YARD_TEST_LISTENERS"
expect_error "multiple processes listen" "$yard" stop worker

# Use an isolated loopback server on an available high port.
port=
for ((attempt=0; attempt<5; attempt++)); do
    candidate=$((20000 + RANDOM))
    "$yard" serve "$candidate" >"$scratch/dashboard.log" 2>&1 &
    dashboard=$!
    for ((probe=0; probe<40; probe++)); do
        if ! kill -0 "$dashboard" 2>/dev/null; then break; fi
        if grep -q "Server listening on http://127.0.0.1:$candidate" "$scratch/dashboard.log"; then
            port="$candidate"
            break
        fi
        sleep 0.05
    done
    [[ -z "$port" ]] || break
    kill -KILL "$dashboard" 2>/dev/null || true
    wait "$dashboard" 2>/dev/null || true
    dashboard=
done
[[ -n "$port" ]] || { cat "$scratch/dashboard.log"; fail "could not start the dashboard"; }
url="http://127.0.0.1:$port"
curl -qfsS -D "$scratch/headers" "$url/" >"$scratch/page"
grep -qi '^X-Frame-Options: DENY' "$scratch/headers"
grep -qi '^Cache-Control: no-store' "$scratch/headers"
token="$(sed -nE "s/.*const YARD_TOKEN='([A-Za-z0-9_-]{43})'.*/\1/p" "$scratch/page")"
[[ ${#token} == 43 ]] || fail "dashboard is missing its action token"
if command -v node >/dev/null 2>&1; then
    sed -nE 's/.*<script>(.*)<\/script>.*/\1/p' "$scratch/page" >"$scratch/dashboard.js"
    [[ -s "$scratch/dashboard.js" ]] || fail "dashboard script was missing"
    node --check "$scratch/dashboard.js"
fi
request_status() { curl -qsS -o "$scratch/response" -w '%{http_code}' "$@"; }
post() {
    request_status -H 'Content-Type: application/json' -d "$2" "$url$1"
}

[[ "$(request_status -H 'Host: external.invalid' "$url/")" == 403 ]]
[[ "$(request_status -H 'Host: external.invalid' "$url/api/ports")" == 403 ]]
[[ "$(request_status -H 'Origin: http://external.invalid' "$url/api/summary")" == 403 ]]
[[ "$(request_status "http://localhost:$port/api/ports")" == 200 ]]
[[ "$(post "/api/processes/$disposable/stop" '{}')" == 403 ]]
[[ "$(post "/api/processes/$disposable/stop" "{\"token\":\"$token\"}")" == 200 ]]
grep -q '"needs_confirm":true' "$scratch/response"
[[ "$(post "/api/processes/$$/stop" "{\"token\":\"$token\"}")" == 200 ]]
grep -q 'is not a detected TCP listener' "$scratch/response"
[[ "$(post "/api/processes/$disposable/force-stop" "{\"token\":\"$token\"}")" == 200 ]]
grep -q '"needs_confirm":true' "$scratch/response"

# Check the actual logs endpoint and truncation metadata.
printf 'first\nsecond\n' >"$YARD_DIR/logs/worker.log"
curl -qfsS "$url/api/services/worker/logs" >"$scratch/response"
grep -q '"lines":\["first","second"\]' "$scratch/response"
awk 'BEGIN { for (i=0; i<290000; i++) printf "x"; print ""; print "last" }' >"$YARD_DIR/logs/worker.log"
curl -qfsS "$url/api/services/worker/logs" >"$scratch/response"
grep -q '"lines":\["last"\]' "$scratch/response"
grep -q '"truncated":true' "$scratch/response"
curl -qfsS "$url/api/services?health=0" >"$scratch/response"
grep -q '"sensitive":true' "$scratch/response"
[[ "$(post "/api/services/worker/start" "{\"token\":\"$token\"}")" == 200 ]]
grep -q 'multiple processes listen' "$scratch/response"
rm "$YARD_TEST_LISTENERS"
[[ "$(request_status -H "Origin: $url" -H 'Content-Type: application/json' -d "{\"token\":\"$token\"}" "$url/api/services/other/stop")" == 200 ]]
grep -q 'no running process found' "$scratch/response"
[[ "$(post "/api/services/other/start" "{\"token\":\"$token\"}")" == 200 ]]
grep -q '"ok":true' "$scratch/response"
[[ "$(post "/api/services/other/stop" "{\"token\":\"$token\"}")" == 200 ]]
grep -q '"signal":"TERM"' "$scratch/response"

# A real probe from the CLI reaches the dashboard, while the dashboard
# itself skips probing its public listener.
printf 'fixture %s dev 3u IPv4 0x1 0t0 TCP 127.0.0.1:%s (LISTEN)\n' "$dashboard" "$port" >"$YARD_TEST_LISTENERS"
"$yard" scan --json >"$scratch/response"
grep -q '"health_status": "healthy"' "$scratch/response"
curl -qfsS "$url/api/services" >"$scratch/response"
if grep -q '"health_status":"timeout"' "$scratch/response"; then
    fail "dashboard health scan probed itself"
fi

printf 'Yard CLI and loopback HTTP integration passed\n'
