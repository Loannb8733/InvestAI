#!/usr/bin/env bash
# Installation unique d'une VM Ubuntu 24.04 (Oracle Cloud, Ampere A1) pour l'API InvestAI.
# A lancer en tant qu'utilisateur ubuntu : bash setup-vm.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Loannb8733/InvestAI.git}"
APP_DIR="$HOME/InvestAI"

sudo apt-get update
sudo apt-get install -y ca-certificates curl git iptables-persistent

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"

for port in 80 443; do
  sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 6 -p tcp --dport "$port" -j ACCEPT
done
sudo iptables -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 6 -p udp --dport 443 -j ACCEPT
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
