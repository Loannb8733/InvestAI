#!/usr/bin/env bash
# Met a jour l'API sur la VM : derniere version de main, reconstruction, redemarrage sans couper Redis ni Caddy.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/InvestAI}"
cd "$APP_DIR"
git fetch --quiet origin main
git reset --quiet --hard origin/main

cd deploy/oracle
test -f .env || { echo ".env absent : copier .env.example et le remplir"; exit 1; }
docker compose build api
docker compose up -d --remove-orphans
docker image prune -f >/dev/null

for _ in $(seq 1 30); do
  if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" 2>/dev/null; then
    echo "API en ligne : $(git -C "$APP_DIR" log -1 --format='%h %s')"
    exit 0
  fi
  sleep 5
done
echo "L'API ne repond pas apres 150 s :"
docker compose logs --tail 50 api
exit 1
