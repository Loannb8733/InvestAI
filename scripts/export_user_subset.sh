#!/usr/bin/env bash
# ============================================================================
# export_user_subset.sh — extrait le sous-arbre d'UN utilisateur depuis la prod
#
# Objectif : rejouer FIN-01 (et tout autre calcul) sur des données réelles sans
# jamais faire sortir de la prod les données des autres utilisateurs. Le filtre
# est appliqué À LA SOURCE : chaque requête porte un WHERE sur l'utilisateur
# cible, donc les autres lignes ne sont même pas lues.
#
# LECTURE SEULE côté prod : uniquement des SELECT via \copy ... TO.
#
# Usage :
#   export PROD_DATABASE_URL="postgresql://...:...@...:5432/postgres"
#   bash scripts/export_user_subset.sh <user_id|email> [dossier_sortie]
#
# Puis import dans une base LOCALE SÉPARÉE (jamais la base de dev en place) :
#   bash scripts/export_user_subset.sh --import <dossier>
# ============================================================================
set -euo pipefail

OUT_DIR="${2:-/tmp/investai_subset}"

# Ordre topologique : un parent est toujours exporté (et réimporté) avant ses
# enfants, sinon les FK rejettent l'insertion.
# Chaque entrée : table|prédicat SQL (utilise $UID, l'utilisateur cible).
TABLES=(
  "users|id = '\$UID'"
  "portfolios|user_id = '\$UID'"
  "assets|portfolio_id IN (SELECT id FROM portfolios WHERE user_id = '\$UID')"
  "transactions|asset_id IN (SELECT a.id FROM assets a JOIN portfolios p ON p.id = a.portfolio_id WHERE p.user_id = '\$UID')"
  "portfolio_snapshots|user_id = '\$UID'"
  "api_keys|user_id = '\$UID'"
  "cold_wallet_addresses|user_id = '\$UID'"
  "goals|user_id = '\$UID'"
  "notes|user_id = '\$UID'"
  "alerts|user_id = '\$UID'"
  "strategies|user_id = '\$UID'"
  "strategy_actions|strategy_id IN (SELECT id FROM strategies WHERE user_id = '\$UID')"
  "planned_orders|user_id = '\$UID'"
  "simulations|user_id = '\$UID'"
  "crowdfunding_projects|asset_id IN (SELECT a.id FROM assets a JOIN portfolios p ON p.id = a.portfolio_id WHERE p.user_id = '\$UID')"
  "crowdfunding_repayments|user_id = '\$UID'"
  "crowdfunding_payment_schedules|project_id IN (SELECT cp.id FROM crowdfunding_projects cp JOIN assets a ON a.id = cp.asset_id JOIN portfolios p ON p.id = a.portfolio_id WHERE p.user_id = '\$UID')"
  "project_audits|user_id = '\$UID'"
  "project_documents|user_id = '\$UID'"
  "calendar_events|user_id = '\$UID'"
  "notifications|user_id = '\$UID'"
  "prediction_logs|user_id = '\$UID'"
  # Table de référence, sans FK utilisateur : les taux de change historiques.
  "fx_daily_rates|true"
)

if [ "${1:-}" = "--import" ]; then
  DIR="${2:?indiquez le dossier contenant les CSV exportes}"
  : "${LOCAL_DATABASE_URL:?LOCAL_DATABASE_URL doit pointer sur une base LOCALE dédiée}"
  echo "Import vers la base locale dédiée..."
  for entry in "${TABLES[@]}"; do
    t="${entry%%|*}"
    [ -s "${DIR}/${t}.csv" ] || { echo "  ${t}: vide, ignoré"; continue; }
    psql "$LOCAL_DATABASE_URL" -c "\copy ${t} FROM '${DIR}/${t}.csv' WITH (FORMAT csv, HEADER true)"
  done
  echo "Import terminé."
  exit 0
fi

: "${PROD_DATABASE_URL:?PROD_DATABASE_URL non défini}"
TARGET="${1:?user_id ou email requis}"
mkdir -p "$OUT_DIR"

# Résout l'email en UUID le cas échéant, pour que le reste du script n'ait
# affaire qu'à un identifiant.
UID_RESOLVED=$(psql "$PROD_DATABASE_URL" -tAc \
  "SELECT id FROM users WHERE id::text = '${TARGET}' OR email = '${TARGET}' LIMIT 1")
if [ -z "$UID_RESOLVED" ]; then
  echo "ERREUR: aucun utilisateur ne correspond à '${TARGET}'" >&2
  exit 1
fi
echo "Utilisateur cible résolu (les données des autres comptes ne seront pas lues)."

for entry in "${TABLES[@]}"; do
  t="${entry%%|*}"
  raw_pred="${entry#*|}"
  pred="${raw_pred//\$UID/$UID_RESOLVED}"
  # Si la base cible est connue, on n'exporte QUE les colonnes qu'elle sait
  # recevoir : les deux schémas peuvent diverger d'une migration (une colonne
  # présente d'un seul côté ferait échouer le COPY à l'import).
  cols="*"
  if [ -n "${LOCAL_DATABASE_URL:-}" ]; then
    common=$(psql "$LOCAL_DATABASE_URL" -tAc \
      "SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
       FROM information_schema.columns
       WHERE table_schema='public' AND table_name='${t}'" 2>/dev/null || true)
    [ -n "$common" ] && cols="$common"
  fi
  psql "$PROD_DATABASE_URL" -c \
    "\copy (SELECT ${cols} FROM ${t} WHERE ${pred}) TO '${OUT_DIR}/${t}.csv' WITH (FORMAT csv, HEADER true)" \
    >/dev/null 2>&1 || { echo "  ${t}: absente ou inaccessible, ignorée"; continue; }
  # Compté côté serveur : `wc -l` surcompte les tables dont un champ JSON
  # contient des retours à la ligne (le CSV les préserve entre guillemets).
  n=$(psql "$PROD_DATABASE_URL" -tAc "SELECT count(*) FROM ${t} WHERE ${pred}" 2>/dev/null || echo "?")
  printf "  %-32s %6s enregistrement(s)\n" "$t" "$n"
done

echo
echo "Export terminé dans ${OUT_DIR}"
echo "Rappel : ces fichiers contiennent vos données réelles — ne les commitez pas."
