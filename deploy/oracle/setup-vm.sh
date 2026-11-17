#!/usr/bin/env bash
# Installation unique d'une VM Ubuntu 24.04 (Oracle Cloud, Ampere A1) pour l'API InvestAI.
# A lancer en tant qu'utilisateur ubuntu : bash setup-vm.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Loannb8733/InvestAI.git}"
APP_DIR="$HOME/InvestAI"

echo "iptables-persistent iptables-persistent/autosave_v4 boolean true" | sudo debconf-set-selections
echo "iptables-persistent iptables-persistent/autosave_v6 boolean true" | sudo debconf-set-selections
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl git iptables-persistent

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"

# Les ouvertures doivent preceder le REJECT final de l'image Oracle, dont la position varie selon l'image
# (5 sur Ubuntu 24.04 aarch64 de novembre 2026) : on retire d'eventuelles regles mal placees puis on insere
# juste avant lui.
for rule in "tcp 80" "tcp 443" "udp 443"; do
  set -- $rule
  while sudo iptables -C INPUT -p "$1" --dport "$2" -j ACCEPT 2>/dev/null; do
    sudo iptables -D INPUT -p "$1" --dport "$2" -j ACCEPT
  done
done
REJECT_AT=$(sudo iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" { print $1; exit }')
for rule in "tcp 80" "tcp 443" "udp 443"; do
  set -- $rule
  if [ -n "$REJECT_AT" ]; then
    sudo iptables -I INPUT "$REJECT_AT" -p "$1" --dport "$2" -j ACCEPT
  else
    sudo iptables -A INPUT -p "$1" --dport "$2" -j ACCEPT
  fi
done
sudo netfilter-persistent save

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi

if [ ! -f "$APP_DIR/deploy/oracle/.env" ]; then
  cp "$APP_DIR/deploy/oracle/.env.example" "$APP_DIR/deploy/oracle/.env"
  chmod 600 "$APP_DIR/deploy/oracle/.env"
  echo "Remplir $APP_DIR/deploy/oracle/.env puis lancer : bash $APP_DIR/deploy/oracle/deploy.sh"
fi

echo "Installation terminee. Se deconnecter puis se reconnecter pour utiliser docker sans sudo."
