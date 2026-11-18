#!/usr/bin/env bash
# Met a jour l'API et le worker sur la VM, reconstruction, redemarrage sans couper Redis ni Caddy.
#
# Sans argument : derniere version de main (usage a la main). Avec un commit en argument, celui que le workflow
# Deploy Oracle envoie : exactement ce commit, celui dont la CI vient de passer, et non la tete de main, qui peut
# porter un merge plus recent dont la CI tourne encore. Quand la cle de deploiement est restreinte a ce script
# (command= dans authorized_keys), l'argument arrive par SSH_ORIGINAL_COMMAND. Un commit absent de main est
# refuse ; un commit plus ancien que celui en place est ignore, pour qu'une CI qui finit en retard ne fasse pas
# revenir en arriere.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/InvestAI}"
TARGET="${1:-}"
case "${SSH_ORIGINAL_COMMAND:-}" in
  *deploy.sh\ *) TARGET="${TARGET:-${SSH_ORIGINAL_COMMAND##* }}" ;;
esac

cd "$APP_DIR"
git fetch --quiet origin main
if [ -n "$TARGET" ]; then
  [[ "$TARGET" =~ ^[0-9a-f]{7,40}$ ]] || { echo "Commit invalide : $TARGET"; exit 1; }
  git merge-base --is-ancestor "$TARGET" origin/main 2>/dev/null || { echo "$TARGET n'est pas sur main : refuse"; exit 1; }
  if [ "$(git rev-parse HEAD)" != "$(git rev-parse "$TARGET")" ] && git merge-base --is-ancestor "$TARGET" HEAD; then
    echo "Deja plus recent que $TARGET : $(git log -1 --format='%h %s'), rien a faire"
    exit 0
  fi
else
  TARGET=origin/main
fi
git reset --quiet --hard "$TARGET"

cd deploy/oracle
test -f .env || { echo ".env absent : copier .env.example et le remplir"; exit 1; }
docker compose build
docker compose up -d --remove-orphans
docker image prune -f >/dev/null

for _ in $(seq 1 30); do
  if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" 2>/dev/null; then
    echo "API en ligne : $(git -C "$APP_DIR" log -1 --format='%h %s')"
    docker compose ps worker
    exit 0
  fi
  sleep 5
done
echo "L'API ne repond pas apres 150 s :"
docker compose logs --tail 50 api
exit 1
