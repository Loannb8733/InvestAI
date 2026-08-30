#!/usr/bin/env bash
# Lance InvestAI en pointant vers Ollama Windows (GPU Intel Arc).
# L'IP de la passerelle WSL change a chaque redemarrage : on la resout ici.
set -euo pipefail

WINDOWS_HOST="$(ip route | awk '/^default/{print $3}')"
export WINDOWS_HOST

echo "Ollama (GPU Windows) : http://${WINDOWS_HOST}:11435"

if curl -sf --max-time 5 "http://${WINDOWS_HOST}:11435/api/version" >/dev/null 2>&1; then
  echo "  -> joignable"
else
  echo "  -> INJOIGNABLE. Verifiez qu'Ollama tourne cote Windows :"
  echo "     %LOCALAPPDATA%\\Programs\\Ollama\\ollama.exe serve"
  echo "  (le backend basculera sur Gemini/Groq si configure)"
fi

# "${@:-up -d}" s'expanserait en UN seul mot ("up -d"), que docker compose
# rejette : on positionne le defaut dans les parametres avant de le passer.
if [ "$#" -eq 0 ]; then
  set -- up -d
fi

docker compose "$@"
