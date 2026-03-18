#!/usr/bin/env bash
# scripts/fix-docker-dns-linux.sh
# Configures Docker to use public DNS servers (Cloudflare + Google) instead of
# systemd-resolved's loopback address (127.0.0.53), which is unreachable from
# inside containers.
#
# Safe: backs up any existing daemon.json before modifying it.
# Only applies to Linux. Requires sudo.

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

# ── OS guard ─────────────────────────────────────────────────────────────────
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

# ── 1. Backup existing daemon.json ───────────────────────────────────────────
if [[ -f "$DAEMON_JSON" ]]; then
    BACKUP="${DAEMON_JSON}.bak.$(date +%Y%m%d_%H%M%S)"
    cp "$DAEMON_JSON" "$BACKUP"
    warn "Existing $DAEMON_JSON backed up to $BACKUP"
fi

# ── 2. Write new daemon.json ─────────────────────────────────────────────────
mkdir -p /etc/docker
cat > "$DAEMON_JSON" <<'EOF'
{
  "dns": ["1.1.1.1", "8.8.8.8"]
}
EOF

ok "Written $DAEMON_JSON with DNS servers: 1.1.1.1 (Cloudflare), 8.8.8.8 (Google)"

# ── 3. Restart Docker ────────────────────────────────────────────────────────
echo ""
echo "   Restarting Docker daemon..."
systemctl restart docker

ok "Docker daemon restarted"

# ── 4. Validate fix ──────────────────────────────────────────────────────────
echo ""
echo "   Validating DNS resolution inside containers..."

if docker run --rm python:3.12-slim python -c "$DNS_TEST_CMD" &>/dev/null; then
    ok "DNS resolution inside containers is now working"
    echo ""
    echo "Fix applied successfully. Run 'make doctor' to confirm all checks pass."
    echo ""
    exit 0
fi

fail "DNS resolution still failing after the fix."
echo ""
echo "    Your network or firewall may be blocking outbound DNS traffic."
echo "    Check that ports 53 (UDP/TCP) are open to 1.1.1.1 and 8.8.8.8."
echo ""
exit 1
