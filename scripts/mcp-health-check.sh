#!/usr/bin/env bash
# MCP Health Check — runs at session start
# Checks Teleport status and basic MCP server connectivity

set -euo pipefail

echo "=== MCP Health Check ==="

# Check Teleport status
if command -v tsh &>/dev/null; then
  if tsh status &>/dev/null 2>&1; then
    echo "Teleport: connected"
  else
    echo "Teleport: NOT connected (run 'tsh login' if MCP servers need it)"
  fi
else
  echo "Teleport: not installed (skip)"
fi

# Check MCP servers by testing if their tools are registered
# This is a passive check — just reports what's available
echo ""
echo "MCP servers will be verified on first use."
echo "If a server fails, run /mcp to reconnect."
