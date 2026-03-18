#!/usr/bin/env bash
# scripts/fix-docker-dns-linux.sh
#
# Safely configures Docker to use public DNS servers (Cloudflare + Google)
# instead of systemd-resolved's loopback address (127.0.0.53), which is
# unreachable from inside containers.
#
# Safety guarantees:
#   - Backs up existing daemon.json before any modification
#   - Merges the "dns" key into existing config (never overwrites other keys)
#   - Aborts if existing JSON is invalid
#   - Idempotent: running multiple times produces the same result
#   - Only applies to Linux; requires sudo

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✅ $*${NC}"; }
fail() { echo -e "${RED}❌ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }

DAEMON_JSON="/etc/docker/daemon.json"
DNS_TEST_CMD='import urllib.request; urllib.request.urlopen("https://pypi.org", timeout=10)'

# ── OS guard ──────────────────────────────────────────────────────────────────
if [[ "$(uname -s)" != "Linux" ]]; then
    warn "This script is intended for Linux only."
    warn "On macOS or Windows, configure DNS through Docker Desktop → Settings → Docker Engine."
    exit 1
fi

# ── Root guard ────────────────────────────────────────────────────────────────
if [[ "$EUID" -ne 0 ]]; then
    fail "This script must be run with sudo:"
    echo ""
    echo "    sudo ${BASH_SOURCE[0]}"
    echo ""
    exit 1
fi

echo ""
echo "🔧 Applying Docker DNS fix for Linux..."
echo ""

# ── 1. Backup existing daemon.json ────────────────────────────────────────────
if [[ -f "$DAEMON_JSON" ]]; then
    BACKUP="${DAEMON_JSON}.bak.$(date +%Y%m%d_%H%M%S)"
    cp "$DAEMON_JSON" "$BACKUP"
    warn "Existing $DAEMON_JSON backed up to $BACKUP"
fi

# ── 2. Merge "dns" field into daemon.json (preserve other keys) ───────────────
mkdir -p /etc/docker

python3 - <<'PY'
import json, sys, os

path = "/etc/docker/daemon.json"

# Load existing config, or start fresh
if os.path.exists(path):
    try:
        with open(path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: {path} contains invalid JSON and cannot be safely updated.")
        print(f"       {e}")
        print(f"       Restore from the backup created above, or delete the file and re-run.")
        sys.exit(1)
else:
    config = {}

# Merge — only update the "dns" key, leave everything else untouched
config["dns"] = ["1.1.1.1", "8.8.8.8"]

with open(path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PY

ok "Updated $DAEMON_JSON — set dns: [\"1.1.1.1\", \"8.8.8.8\"] (other settings preserved)"

# ── 3. Restart Docker ─────────────────────────────────────────────────────────
echo ""
echo "   Restarting Docker daemon..."

if command -v systemctl &>/dev/null && systemctl list-units --type=service 2>/dev/null | grep -q 'docker.service'; then
    systemctl restart docker
    ok "Docker daemon restarted via systemctl"
else
    warn "docker.service not found in systemd (Docker Desktop or custom install)."
    warn "Please restart Docker manually, then re-run 'make doctor'."
    echo ""
    echo "    Common ways to restart Docker:"
    echo "      • Docker Desktop: quit and reopen from the system tray"
    echo "      • Manual daemon: sudo dockerd &"
    echo ""
    exit 0
fi

# ── 4. Validate fix ───────────────────────────────────────────────────────────
echo ""
echo "   Validating DNS resolution inside containers..."

if docker run --rm python:3.12-slim python -c "$DNS_TEST_CMD" &>/dev/null; then
    ok "DNS resolution inside containers is now working"
    echo ""
    echo "Fix applied successfully. Run 'make doctor' to confirm all checks pass."
    echo ""
    exit 0
fi

fail "DNS resolution is still failing after the fix."
echo ""
echo "    Possible causes:"
echo "      • Firewall blocking outbound traffic to 1.1.1.1 / 8.8.8.8 on port 53"
echo "      • VPN or proxy intercepting DNS queries inside containers"
echo "      • Corporate network restricting external DNS resolvers"
echo "      • Docker daemon networking misconfiguration beyond DNS"
echo ""
echo "    Next steps:"
echo "      1. Check Docker daemon logs: sudo journalctl -u docker --since '5 min ago'"
echo "      2. Verify outbound connectivity: curl -v https://pypi.org"
echo "      3. Inspect the current config: cat $DAEMON_JSON"
echo ""
exit 1
