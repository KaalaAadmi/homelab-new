#!/bin/bash
# Limits who can reach the ports that Docker publishes.
#
# Why: Docker opens published ports in its own firewall chains, which skip ufw/firewalld,
# so without this every container port is open to every device on your home Wi-Fi.
#
# After this runs:
#   - Tailscale (your devices), localhost and other containers can reach every published port.
#   - Devices on the home network can reach only LAN_ALLOWED_TCP / LAN_ALLOWED_UDP below:
#     Caddy (80/443, where the Authentik login protects apps that have none), DNS (53),
#     Jellyfin (8096, for TV apps) and MQTT (1883, for smart-home devices).
#   - Everything else from the home network (or the internet) is dropped.
#
# Home Assistant runs on the host network, so ufw covers it, not this script.
set -euo pipefail

LAN_ALLOWED_TCP="80 443 53 8096 1883"
LAN_ALLOWED_UDP="53"
CONTAINER_NETS="172.16.0.0/12"     # Docker's default address pools
TAILSCALE_NET="100.64.0.0/10"

# The interface that faces your home network (the one with the default route)
LAN_IF="${LAN_IF:-$(ip route show default | awk '{print $5; exit}')}"
if [ -z "$LAN_IF" ]; then echo "no default route yet; try again later" >&2; exit 1; fi

ipt() { iptables "$@"; }

# DOCKER-USER exists once Docker has started; create it if we run first.
ipt -n -L DOCKER-USER >/dev/null 2>&1 || ipt -N DOCKER-USER
ipt -F DOCKER-USER

ipt -A DOCKER-USER -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN
ipt -A DOCKER-USER -s "$CONTAINER_NETS" -j RETURN
ipt -A DOCKER-USER -i tailscale0 -j RETURN
ipt -A DOCKER-USER -s "$TAILSCALE_NET" -j RETURN
ipt -A DOCKER-USER ! -i "$LAN_IF" -j RETURN            # only filter traffic arriving from the LAN

# Docker has already rewritten the destination port by the time packets reach this chain,
# so match the port the client originally asked for (--ctorigdstport).
for p in $LAN_ALLOWED_TCP; do
  ipt -A DOCKER-USER -i "$LAN_IF" -p tcp -m conntrack --ctorigdstport "$p" --ctdir ORIGINAL -j RETURN
done
for p in $LAN_ALLOWED_UDP; do
  ipt -A DOCKER-USER -i "$LAN_IF" -p udp -m conntrack --ctorigdstport "$p" --ctdir ORIGINAL -j RETURN
done

ipt -A DOCKER-USER -i "$LAN_IF" -m conntrack --ctstate NEW -j DROP
ipt -A DOCKER-USER -j RETURN

# fail2ban keeps its Vaultwarden bans in this chain too; flushing removed its hook, so restart it.
if systemctl is-active --quiet fail2ban; then systemctl restart fail2ban; fi

echo "DOCKER-USER rules applied on $LAN_IF:"
ipt -S DOCKER-USER
