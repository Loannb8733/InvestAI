"""Unit tests for the shared FIFO primitives (HIGH — cost-basis unification).

These functions are now the single source of truth consumed by both
metrics_service (displayed P&L) and report_service (tax 2086 / sell estimates),
so pinning them here guards against the two engines diverging.
"""

from decimal import Decimal

from app.services.fifo import consume_fifo, consume_fifo_with_dates, extract_fifo_layers


def _layers():
    return [
        {"qty": Decimal("2"), "unit_cost": Decimal("100"), "acquired_at": "2026-01-01"},
        {"qty": Decimal("3"), "unit_cost": Decimal("200"), "acquired_at": "2026-02-01"},
    ]


class TestConsumeFifo:
    def test_partial_first_layer(self):
        layers = _layers()
        cost = consume_fifo(layers, Decimal("1"))
        assert cost == Decimal("100")  # 1 @ 100
        assert layers[0]["qty"] == Decimal("1")  # layer decremented in place

    def test_crosses_layers(self):
        layers = _layers()
        cost = consume_fifo(layers, Decimal("4"))  # 2@100 + 2@200
        assert cost == Decimal("600")
        assert len(layers) == 1 and layers[0]["qty"] == Decimal("1")

    def test_full_then_underflow_is_graceful(self):
        layers = _layers()
        cost = consume_fifo(layers, Decimal("10"))  # only 5 available
        assert cost == Decimal("800")  # 2@100 + 3@200
        assert layers == []


class TestConsumeFifoWithDates:
    def test_returns_oldest_acquired_at(self):
        layers = _layers()
        cost, oldest = consume_fifo_with_dates(layers, Decimal("3"))
        assert cost == Decimal("400")  # 2@100 + 1@200
        assert oldest == "2026-01-01"


class TestExtractFifoLayers:
    def test_extract_preserves_unit_costs_and_keys(self):
        layers = _layers()
        extracted = extract_fifo_layers(layers, Decimal("3"))
        # 2 @100 (whole) + 1 @200 (partial)
        assert [(e["qty"], e["unit_cost"]) for e in extracted] == [
            (Decimal("2"), Decimal("100")),
            (Decimal("1"), Decimal("200")),
        ]
        assert extracted[1]["acquired_at"] == "2026-02-01"  # partial keeps metadata
        assert layers[0]["qty"] == Decimal("2")  # remainder stays as one layer

    def test_consume_and_extract_remove_same_quantity(self):
        # Cross-engine guarantee: cost removed by consume_fifo equals the summed
        # cost of the layers extracted by extract_fifo_layers for the same qty.
        a, b = _layers(), _layers()
        cost = consume_fifo(a, Decimal("4"))
        extracted = extract_fifo_layers(b, Decimal("4"))
        extracted_cost = sum(e["qty"] * e["unit_cost"] for e in extracted)
        assert cost == extracted_cost == Decimal("600")
