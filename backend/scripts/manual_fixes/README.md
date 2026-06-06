# Manual data fixes — InvestAI prod

One-shot scripts that correct data anomalies in the production database. Each
script is **idempotent and dry-run by default** — re-running it after the
correction is already applied is safe. Pass `--apply` to actually write.

Why are these here? The wave-7 data audit (`scripts/check_invariants.py`)
surfaced a handful of legacy issues in prod that the upstream sync code can't
fix on its own. They are committed so that:

1. The corrections are reproducible — a future contributor (or a re-deploy
   wiping a staging DB) can replay them in seconds instead of investigating
   from scratch.
2. If a "Reset & re-import" workflow ever wipes the affected transactions,
   running these scripts back-to-back restores the corrected state.

Run order (all read DATABASE_URL from the env):

```bash
DATABASE_URL='postgresql://…' python -m scripts.manual_fixes.2026_06_06_pepe_vouchers_insert       # dry-run
DATABASE_URL='…' python -m scripts.manual_fixes.2026_06_06_pepe_vouchers_insert --apply

DATABASE_URL='…' python -m scripts.manual_fixes.2026_06_06_fet_orphan_delete                       # dry-run
DATABASE_URL='…' python -m scripts.manual_fixes.2026_06_06_fet_orphan_delete --apply

DATABASE_URL='…' python -m scripts.manual_fixes.2026_06_06_convert_zero_price_fix                  # dry-run
DATABASE_URL='…' python -m scripts.manual_fixes.2026_06_06_convert_zero_price_fix --apply
```

After each run, re-check invariants:

```bash
DATABASE_URL='…' python -m scripts.check_invariants
```

## What each fix does

### `2026_06_06_pepe_vouchers_insert.py`
Inserts two `AIRDROP` transactions for the two `20 000 PEPE` Binance reward
vouchers redeemed on 2026-03-25. The Binance sync does not see the rewards
API, so this fills a 40 000 PEPE hole that otherwise made
`computed_qty(PEPE) < stored_qty` by exactly that amount. Price is the
EUR-equivalent of PEPE on that day (≈ 0.00000344 €/PEPE — fetched from Yahoo
historical at fix time).

### `2026_06_06_fet_orphan_delete.py`
Removes one orphan `SELL 122.3 FET` row from Binance whose `external_id` is
empty and whose `notes` claim a trade ID that does not appear in any other
record (`Spot trade FET/USDC #182676642`). The user confirmed the trade was
never present in Binance Spot History — it was a duplicate of the legitimate
`SELL 122.3 FET ext=8382194`, almost certainly an early manual import that
predates external_id tracking.

### `2026_06_06_convert_zero_price_fix.py`
Updates `price` on 9 Binance Convert rows that were synced with `price=0` €,
which made cost-basis FIFO underweight the EUR value paid for the received
asset. Each price is recomputed as
`(sibling_USD_qty × USD/EUR rate of the day) / self_qty`, using
`fx_daily_rates` for the historical USD→EUR rate. Skipped: 19 rows whose
sibling is a non-USD crypto (PEPE↔DOGE/ETH/SOL/PAXG) — those need
historical CoinGecko prices and are a follow-up.

## Re-import safety

A standard incremental sync (hourly cron, dashboard refresh button) preserves
all of these corrections because:
- the delete-driven fixes correspond to rows the sync code no longer produces
  (PR #210 narrowed `get_fiat_orders` to true fiat),
- the insert is keyed on `external_id`s that don't appear in any Binance API
  endpoint, so the sync has no way to recreate them,
- the price updates touch existing rows whose `external_id` is already
  tracked, so the sync's "skip if external_id seen" guard leaves them alone.

A **full reset & re-sync** of the Binance API key would lose the PEPE vouchers
and the corrected prices. If you do that, rerun the scripts in order
afterwards.
