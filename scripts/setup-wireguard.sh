#!/bin/bash
# WireGuard VPN setup for webgrab VM
# This script installs and configures WireGuard to bypass IP blocks
# Expects WIREGUARD_PRIVATE_KEY and WIREGUARD_PSK environment variables

set -e

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root or with sudo"
    exit 1
fi

# Validate required env vars
if [ -z "$WIREGUARD_PRIVATE_KEY" ]; then
    echo "ERROR: WIREGUARD_PRIVATE_KEY not set"
    exit 1
fi

if [ -z "$WIREGUARD_PSK" ]; then
    echo "ERROR: WIREGUARD_PSK not set"
    exit 1
fi

# Install wireguard-tools
if ! command -v wg &> /dev/null; then
    echo "Installing WireGuard..."
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq wireguard-tools
fi

# Create wireguard config directory
mkdir -p /etc/wireguard

# Write the config file with keys from environment variables
cat > /etc/wireguard/wg0.conf << EOF
[Interface]
Address = 10.139.40.237/32
PrivateKey = ${WIREGUARD_PRIVATE_KEY}
MTU = 1320
DNS = 10.128.0.1

[Peer]
PublicKey = PyLCXAQT8KkM4T+dUsOQfn+Ub3pGxfGlxkIApuig+hk=
PresharedKey = ${WIREGUARD_PSK}
Endpoint = 146.70.179.196:1637
AllowedIPs = 0.0.0.0/0,::/0
PersistentKeepalive = 15
EOF

# Set permissions
chmod 600 /etc/wireguard/wg0.conf

# Enable and start the service
systemctl enable wg-quick@wg0
systemctl restart wg-quick@wg0 || systemctl start wg-quick@wg0

echo "WireGuard setup complete."
echo "Interface status:"
wg show wg0 2>/dev/null || echo "wg0 not yet active"
