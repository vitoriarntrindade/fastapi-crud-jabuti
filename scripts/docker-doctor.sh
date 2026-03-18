#!/usr/bin/env bash
# scripts/docker-doctor.sh
# Preflight checks for the Docker environment.
# Validates that Docker is running and that containers have working DNS.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ok()   { echo -e "${GREEN}✅ $*${NC}"; }
fail() { echo -e "${RED}❌ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "🔍 Running Docker preflight checks..."
echo ""

# ── 1. Docker installed ──────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    fail "Docker is not installed"
    echo ""
    echo "    Install Docker: https://docs.docker.com/get-docker/"
    echo ""
    exit 1
fi

# ── 2. Docker daemon is running ──────────────────────────────────────────────
if ! docker info &>/dev/null; then
    fail "Docker is installed but the daemon is not running"
    echo ""
    echo "    Start Docker Desktop, or run:"
    echo "        sudo systemctl start docker"
    echo ""
    exit 1
fi

ok "Docker is running"

# ── 3. DNS resolution inside containers ─────────────────────────────────────
DNS_TEST_CMD='import urllib.request; urllib.request.urlopen("https://pypi.org", timeout=10)'

if docker run --rm python:3.12-slim python -c "$DNS_TEST_CMD" &>/dev/null; then
    ok "DNS resolution inside containers is working"
    echo ""
    echo "All checks passed. You are ready to go 🚀"
    echo ""
    exit 0
fi

# DNS failed ─────────────────────────────────────────────────────────────────
fail "Docker cannot resolve DNS inside containers"
echo ""
echo "    This is a known issue on Linux systems using systemd-resolved (127.0.0.53)."
echo "    Docker containers cannot reach the host-only loopback DNS resolver."
echo ""
echo "    Suggested fix:"
echo "        ${SCRIPT_DIR}/fix-docker-dns-linux.sh"
echo ""

exit 1
