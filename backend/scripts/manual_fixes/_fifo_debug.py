"""Reproduce backend FIFO for BTC to find the bug. Read-only."""

import asyncio
import os
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ZERO = Decimal("0")


async def main():
    url = (
        os.environ["DATABASE_URL"]
        .replace("postgresql://", "postgresql+asyncpg://", 1)
        .replace("sslmode=require", "ssl=require")
    )
    eng = create_async_engine(url, echo=False)
    async with eng.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT t.transaction_type::text AS tt, t.quantity, t.price,"
                    " t.fee, t.executed_at, t.id::text AS tid, t.external_id,"
                    " t.notes, a.exchange, a.symbol"
                    " FROM transactions t JOIN assets a ON a.id = t.asset_id"
                    " WHERE a.symbol = 'BTC'"
                    " ORDER BY COALESCE(t.executed_at, t.created_at), t.id"
                )
            )
        ).all()
        print(f"Total BTC transactions: {len(rows)}")
        print()

        fifo: dict = defaultdict(list)

        def consume(key, qty):
            extracted = []
            remaining = qty
            while remaining > 0 and fifo[key]:
                layer = fifo[key][0]
                take = layer["qty"] if layer["qty"] <= remaining else remaining
                extracted.append({"qty": take, "unit_cost": layer["unit_cost"]})
                layer["qty"] -= take
                remaining -= take
                if layer["qty"] == 0:
                    fifo[key].pop(0)
            return extracted

        for tt, qty, px, fee, dt, tid, ext, notes, ex, sym in rows:
            qty = Decimal(str(qty))
            px = Decimal(str(px or 0))
            key = (sym, (ex or "").strip())

            if tt in ("BUY", "CONVERSION_IN"):
                if px > 0:
                    fifo[key].append({"qty": qty, "unit_cost": px})
            elif tt == "TRANSFER_OUT":
                extracted = consume(key, qty)
                tkey = (sym, f"__transit__{tid}")
                fifo[tkey] = extracted
                cost = sum(l["qty"] * l["unit_cost"] for l in extracted)
                print(
                    f"  OUT {ex:<12} qty={float(qty):.8f} {dt} -> transit {tid[:8]} "
                    f"layers={len(extracted)} cost={float(cost):.2f}"
                )
            elif tt == "TRANSFER_IN":
                matched = None
                best_diff = None
                for tkey in list(fifo.keys()):
                    if tkey[0] == sym and tkey[1].startswith("__transit__"):
                        tqty = sum(l["qty"] for l in fifo[tkey])
                        diff = abs(tqty - qty)
                        if best_diff is None or diff < best_diff:
                            best_diff = diff
                            matched = tkey
                if matched and fifo[matched]:
                    transit_layers = fifo.pop(matched)
                    tqty = sum(l["qty"] for l in transit_layers)
                    if tqty > qty:
                        temp_key = (sym, f"__trim__{matched[1]}")
                        fifo[temp_key] = transit_layers
                        trimmed = consume(temp_key, qty)
                        fifo.pop(temp_key, None)
                        for layer in trimmed:
                            fifo[key].append(layer)
                        cost = sum(l["qty"] * l["unit_cost"] for l in trimmed)
                        action = f"TRANSIT trim from {matched[1][:18]} cost={float(cost):.2f}"
                    else:
                        for layer in transit_layers:
                            fifo[key].append(layer)
                        cost = sum(l["qty"] * l["unit_cost"] for l in transit_layers)
                        action = f"TRANSIT match from {matched[1][:18]} cost={float(cost):.2f}"
                else:
                    if px > 0:
                        fifo[key].append({"qty": qty, "unit_cost": px})
                        action = f"UNMATCHED tx_price={float(px):.2f} cost={float(qty * px):.2f}"
                    else:
                        action = "UNMATCHED zero-cost"
                print(f"  IN  {ex:<12} qty={float(qty):.8f} {dt} -> {action}")
            elif tt in ("SELL", "CONVERSION_OUT"):
                consume(key, qty)

        print()
        print("=== FINAL FIFO STATE ===")
        for key in sorted(fifo.keys()):
            if key[1].startswith("__transit__"):
                continue
            total_qty = sum(l["qty"] for l in fifo[key])
            total_cost = sum(l["qty"] * l["unit_cost"] for l in fifo[key])
            if total_qty > 0:
                avg = total_cost / total_qty
                print(f"  {key[1]:<14} qty={float(total_qty):.8f} cost={float(total_cost):.2f} avg={float(avg):.2f}")
        print()
        print("=== ORPHAN TRANSIT (cost basis LOST) ===")
        for key in sorted(fifo.keys()):
            if not key[1].startswith("__transit__"):
                continue
            total_qty = sum(l["qty"] for l in fifo[key])
            total_cost = sum(l["qty"] * l["unit_cost"] for l in fifo[key])
            if total_qty > 0:
                print(f"  {key[1][:35]:<35} qty={float(total_qty):.8f} cost={float(total_cost):.2f}")


asyncio.run(main())
