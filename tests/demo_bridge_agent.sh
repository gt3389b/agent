#!/bin/bash
# Demo script showing BridgeAgent with WRP message sniffing

cd "$(dirname "$0")/.."

echo "================================================================================"
echo "USP Bridge Agent Demo - WRP Message Sniffing"
echo "================================================================================"
echo ""
echo "This will demonstrate:"
echo "  1. Get request for a remote parameter (Device.WiFi.Radio.1.Channel)"
echo "  2. WRP message encoding on TX channel"
echo "  3. WRP message decoding on RX channel"
echo "  4. Operation type preserved in metadata"
echo ""
echo "Press Enter to start..."
read

python -m tests.test_bridge_agent_interactive <<EOF
get Device.WiFi.Radio.1.Channel
stats
quit
EOF
