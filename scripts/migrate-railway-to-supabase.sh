#!/usr/bin/env bash
# ============================================================================
# migrate-railway-to-supabase.sh
#
# Exporte les données de Railway PostgreSQL et les importe dans Supabase.
# Gère les 307 transactions crypto + toutes les tables liées.
#
# Usage:
#   export RAILWAY_DATABASE_URL="postgresql://user:pass@host:port/db"
#   export SUPABASE_DATABASE_URL="postgresql://postgres.[ref]:pass@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
#   bash scripts/migrate-railway-to-supabase.sh
#
# Prérequis: pg_dump et psql installés localement
# ============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

DUMP_FILE="/tmp/investai_railway_dump_$(date +%Y%m%d_%H%M%S).sql"

# --- Validation ---
if [ -z "${RAILWAY_DATABASE_URL:-}" ]; then
  echo -e "${RED}ERROR: RAILWAY_DATABASE_URL is not set${NC}"
  echo "  export RAILWAY_DATABASE_URL=\"postgresql://user:pass@host:port/db\""
  exit 1
fi

if [ -z "${SUPABASE_DATABASE_URL:-}" ]; then
  echo -e "${RED}ERROR: SUPABASE_DATABASE_URL is not set${NC}"
  echo "  export SUPABASE_DATABASE_URL=\"postgresql://postgres.[ref]:pass@host:5432/postgres\""
  exit 1
fi

echo -e "${YELLOW}=== InvestAI: Railway → Supabase Migration ===${NC}"
echo ""

# --- Step 1: Count records on Railway ---
echo -e "${GREEN}[1/5] Counting records on Railway...${NC}"
TRANSACTION_COUNT=$(psql "$RAILWAY_DATABASE_URL" -t -A -c "SELECT COUNT(*) FROM transactions;" 2>/dev/null || echo "?")
USER_COUNT=$(psql "$RAILWAY_DATABASE_URL" -t -A -c "SELECT COUNT(*) FROM users;" 2>/dev/null || echo "?")
ASSET_COUNT=$(psql "$RAILWAY_DATABASE_URL" -t -A -c "SELECT COUNT(*) FROM assets;" 2>/dev/null || echo "?")
PORTFOLIO_COUNT=$(psql "$RAILWAY_DATABASE_URL" -t -A -c "SELECT COUNT(*) FROM portfolios;" 2>/dev/null || echo "?")

echo "  Users:        $USER_COUNT"
echo "  Portfolios:   $PORTFOLIO_COUNT"
echo "  Assets:       $ASSET_COUNT"
echo "  Transactions: $TRANSACTION_COUNT"
echo ""

# --- Step 2: Export from Railway ---
echo -e "${GREEN}[2/5] Exporting data from Railway (pg_dump)...${NC}"
pg_dump "$RAILWAY_DATABASE_URL" \
  --no-owner \
  --no-privileges \
  --no-comments \
  --clean \
  --if-exists \
  --format=plain \
  --file="$DUMP_FILE"

DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo "  Dump file: $DUMP_FILE ($DUMP_SIZE)"
echo ""

# --- Step 3: Pre-import checks on Supabase ---
echo -e "${GREEN}[3/5] Verifying Supabase connection...${NC}"
SUPABASE_VERSION=$(psql "$SUPABASE_DATABASE_URL" -t -A -c "SELECT version();" 2>/dev/null | head -1)
if [ -z "$SUPABASE_VERSION" ]; then
  echo -e "${RED}ERROR: Cannot connect to Supabase${NC}"
  exit 1
fi
echo "  Connected: $SUPABASE_VERSION"
echo ""

# --- Step 4: Import into Supabase ---
echo -e "${GREEN}[4/5] Importing data into Supabase...${NC}"
echo -e "${YELLOW}  WARNING: This will DROP and recreate all tables in the target database.${NC}"
read -p "  Continue? [y/N] " -r
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Aborted."
  rm -f "$DUMP_FILE"
  exit 0
fi

psql "$SUPABASE_DATABASE_URL" -f "$DUMP_FILE" 2>&1 | tail -5
echo ""

# --- Step 5: Validate migration ---
echo -e "${GREEN}[5/5] Validating migration...${NC}"
NEW_TRANSACTION_COUNT=$(psql "$SUPABASE_DATABASE_URL" -t -A -c "SELECT COUNT(*) FROM transactions;" 2>/dev/null || echo "0")
NEW_USER_COUNT=$(psql "$SUPABASE_DATABASE_URL" -t -A -c "SELECT COUNT(*) FROM users;" 2>/dev/null || echo "0")
NEW_ASSET_COUNT=$(psql "$SUPABASE_DATABASE_URL" -t -A -c "SELECT COUNT(*) FROM assets;" 2>/dev/null || echo "0")

echo "  Users:        $NEW_USER_COUNT (was $USER_COUNT)"
echo "  Assets:       $NEW_ASSET_COUNT (was $ASSET_COUNT)"
echo "  Transactions: $NEW_TRANSACTION_COUNT (was $TRANSACTION_COUNT)"

if [ "$NEW_TRANSACTION_COUNT" = "$TRANSACTION_COUNT" ]; then
  echo -e "${GREEN}  ✓ Transaction count matches!${NC}"
else
  echo -e "${RED}  ✗ Transaction count mismatch! Expected $TRANSACTION_COUNT, got $NEW_TRANSACTION_COUNT${NC}"
fi

# Cleanup
rm -f "$DUMP_FILE"

echo ""
echo -e "${GREEN}=== Migration complete ===${NC}"
echo ""
echo "Next steps:"
echo "  1. Set DATABASE_URL in Render dashboard to your Supabase connection string"
echo "  2. Run: alembic upgrade head (to ensure schema is up to date)"
echo "  3. Verify Net Worth via API: curl https://investai-api.onrender.com/api/v1/dashboard/summary"
