"""
Dashboard Mathematical Coherence Verification Script.

Runs against the live API to validate that ALL dashboard metrics
are mathematically consistent with the unified root formula:

    P&L = Patrimoine Total - Total Investi

Usage:
    # Against local dev server:
    python -m tests.verify_dashboard_math

    # Against custom URL:
    INVESTAI_API_URL=https://app.example.com/api/v1 python -m tests.verify_dashboard_math

Requires a valid JWT token set via INVESTAI_TOKEN env var,
or uses a test login via INVESTAI_EMAIL / INVESTAI_PASSWORD.
"""

import math
import os
import sys

import httpx

API_URL = os.getenv("INVESTAI_API_URL", "http://localhost:8000/api/v1")
TOKEN = os.getenv("INVESTAI_TOKEN", "")
EMAIL = os.getenv("INVESTAI_EMAIL", "")
PASSWORD = os.getenv("INVESTAI_PASSWORD", "")

# Tolerance for floating-point comparisons (0.02€ or 0.02%)
ABS_TOL = 0.02
REL_TOL = 0.01  # 1% relative tolerance for percentages


def approx_eq(a: float, b: float, atol: float = ABS_TOL) -> bool:
    """Check if two floats are approximately equal."""
    return abs(a - b) <= atol


def pct_eq(a: float, b: float, rtol: float = REL_TOL) -> bool:
    """Check if two percentages are approximately equal (relative)."""
    if abs(b) < 0.01:
        return abs(a - b) < 0.1
    return abs(a - b) / max(abs(b), 1e-9) <= rtol


class DashboardVerifier:
    """Verifies all 22 dashboard metric coherence invariants."""

    def __init__(self, data: dict):
        self.d = data
        self.adv = data.get("advanced_metrics", {})
        self.pnl = self.adv.get("pnl_breakdown", {})
        self.risk = self.adv.get("risk_metrics", {})
        self.conc = self.adv.get("concentration", {})
        self.stress = self.adv.get("stress_tests", [])
        self.errors: list[str] = []
        self.passes: list[str] = []

    def _check(self, name: str, condition: bool, detail: str = ""):
        if condition:
            self.passes.append(f"  PASS  {name}")
        else:
            msg = f"  FAIL  {name}"
            if detail:
                msg += f" -- {detail}"
            self.errors.append(msg)

    def run_all(self) -> bool:
        """Run all checks, return True if all pass."""
        self.check_patrimoine_root()
        self.check_capital_net()
        self.check_plus_value_nette()
        self.check_plus_value_percent()
        self.check_pnl_total_root()
        self.check_pnl_reconciliation()
        self.check_pnl_net_fees()
        self.check_variation_tout()
        self.check_variation_tout_percent()
        self.check_cagr_sign()
        self.check_sharpe_sign_consistency()
        self.check_volatility_range()
        self.check_var_range()
        self.check_max_drawdown_range()
        self.check_hhi_range()
        self.check_stress_test_20()
        self.check_stress_test_40()
        self.check_allocation_sum()
        self.check_gain_loss_equals_net_gain()
        self.check_no_nan()

        print("\n" + "=" * 60)
        print("DASHBOARD MATH VERIFICATION RESULTS")
        print("=" * 60)
        for p in self.passes:
            print(p)
        for e in self.errors:
            print(e)
        print("-" * 60)
        print(f"  {len(self.passes)} passed, {len(self.errors)} failed")
        print("=" * 60)

        return len(self.errors) == 0

    # ── A. BLOC PATRIMOINE ──

    def check_patrimoine_root(self):
        """total_value must be non-negative."""
        tv = self.d["total_value"]
        self._check(
            "A1: Patrimoine >= 0",
            tv >= 0,
            f"total_value={tv}",
        )

    def check_capital_net(self):
        """net_capital = total_invested - (total_invested - net_capital)."""
        nc = self.d["net_capital"]
        ti = self.d["total_invested"]
        # net_capital should be <= total_invested (can't have sold negative)
        self._check(
            "A3: Capital Net <= Total Investi",
            nc <= ti + ABS_TOL,
            f"net_capital={nc:.2f}, total_invested={ti:.2f}",
        )

    # ── B. BLOC P&L ──

    def check_plus_value_nette(self):
        """net_gain_loss = total_value - total_invested (unified root)."""
        expected = self.d["total_value"] - self.d["total_invested"]
        actual = self.d["net_gain_loss"]
        self._check(
            "B1: Plus-value Nette = Patrimoine - Investi",
            approx_eq(actual, expected),
            f"expected={expected:.2f}, actual={actual:.2f}",
        )

    def check_plus_value_percent(self):
        """net_gain_loss_percent = net_gain_loss / total_invested * 100."""
        ti = self.d["total_invested"]
        if ti <= 0:
            return
        expected = (self.d["net_gain_loss"] / ti) * 100
        actual = self.d["net_gain_loss_percent"]
        self._check(
            "B1b: Plus-value % = net_gain_loss / total_invested * 100",
            pct_eq(actual, expected),
            f"expected={expected:.2f}%, actual={actual:.2f}%",
        )

    def check_pnl_total_root(self):
        """total_pnl = total_value - total_invested (same root as plus-value)."""
        expected = self.d["total_value"] - self.d["total_invested"]
        actual = self.pnl.get("total_pnl", 0)
        self._check(
            "B6: P&L Total = Patrimoine - Investi",
            approx_eq(actual, expected),
            f"expected={expected:.2f}, actual={actual:.2f}",
        )

    def check_pnl_reconciliation(self):
        """realized + unrealized = total_pnl (perfect reconciliation)."""
        realized = self.pnl.get("realized_pnl", 0)
        unrealized = self.pnl.get("unrealized_pnl", 0)
        total = self.pnl.get("total_pnl", 0)
        actual_sum = realized + unrealized
        self._check(
            "B3+B4: Realise + Latent = P&L Total",
            approx_eq(actual_sum, total),
            f"realized({realized:.2f}) + unrealized({unrealized:.2f}) = {actual_sum:.2f}, expected={total:.2f}",
        )

    def check_pnl_net_fees(self):
        """net_pnl = total_pnl - total_fees (fees deducted exactly once)."""
        total = self.pnl.get("total_pnl", 0)
        fees = self.pnl.get("total_fees", 0)
        expected = total - fees
        actual = self.pnl.get("net_pnl", 0)
        self._check(
            "B7: P&L Net = P&L Total - Frais",
            approx_eq(actual, expected),
            f"total({total:.2f}) - fees({fees:.2f}) = {expected:.2f}, actual={actual:.2f}",
        )

    # ── C. BLOC VARIATIONS ──

    def check_variation_tout(self):
        """For period 'Tout' (days=0), period_change = total_value - total_invested."""
        if self.d.get("period_days", 30) < 365:
            self.passes.append("  SKIP  C2: Variation Tout (not 'Tout' period)")
            return
        expected = self.d["total_value"] - self.d["total_invested"]
        actual = self.d.get("period_change", 0)
        self._check(
            "C2: Variation Tout = Patrimoine - Investi",
            approx_eq(actual, expected, atol=1.0),
            f"expected={expected:.2f}, actual={actual:.2f}",
        )

    def check_variation_tout_percent(self):
        """For 'Tout', period_change_percent = (P-I)/I * 100."""
        if self.d.get("period_days", 30) < 365:
            self.passes.append("  SKIP  C2b: Variation Tout % (not 'Tout' period)")
            return
        ti = self.d["total_invested"]
        if ti <= 0:
            return
        expected = ((self.d["total_value"] - ti) / ti) * 100
        actual = self.d.get("period_change_percent", 0)
        self._check(
            "C2b: Variation Tout % = (P-I)/I * 100",
            pct_eq(actual, expected),
            f"expected={expected:.2f}%, actual={actual:.2f}%",
        )

    # ── B8. ROI Annualisé ──

    def check_cagr_sign(self):
        """If total_value < total_invested, CAGR must be negative."""
        tv = self.d["total_value"]
        ti = self.d["total_invested"]
        cagr = self.adv.get("roi_annualized", 0)
        if tv < ti:
            self._check(
                "B8: CAGR negatif quand Patrimoine < Investi",
                cagr < 0,
                f"total_value={tv:.2f} < total_invested={ti:.2f} but CAGR={cagr:.2f}%",
            )
        else:
            self.passes.append("  SKIP  B8: CAGR sign (Patrimoine >= Investi)")

    # ── D. BLOC RISQUE ──

    def check_sharpe_sign_consistency(self):
        """If CAGR < risk_free (3.5%), Sharpe must be negative."""
        cagr = self.adv.get("roi_annualized", 0)
        sharpe = self.risk.get("sharpe_ratio", 0)
        if cagr < 3.5:
            self._check(
                "D2: Sharpe negatif quand CAGR < 3.5%",
                sharpe < 0,
                f"CAGR={cagr:.2f}% < 3.5% but Sharpe={sharpe:.2f}",
            )
        else:
            self.passes.append("  SKIP  D2: Sharpe sign (CAGR >= 3.5%)")

    def check_volatility_range(self):
        """Volatility should be in [0%, 300%] for a normal crypto portfolio."""
        vol = self.risk.get("volatility", 0)
        self._check(
            "D1: Volatilite dans [0%, 300%]",
            0 <= vol <= 300,
            f"volatility={vol:.1f}%",
        )

    def check_var_range(self):
        """VaR amount should be between 0 and portfolio value."""
        var_data = self.risk.get("var_95", {})
        var_amount = var_data.get("var_amount", 0)
        tv = self.d["total_value"]
        self._check(
            "D4: VaR 95% dans [0, Patrimoine]",
            0 <= var_amount <= tv + ABS_TOL,
            f"var_amount={var_amount:.2f}, total_value={tv:.2f}",
        )

    def check_max_drawdown_range(self):
        """Max Drawdown should be in [0%, 100%]."""
        mdd = self.risk.get("max_drawdown", {})
        pct = mdd.get("max_drawdown_percent", 0)
        self._check(
            "D3: Max Drawdown dans [0%, 100%]",
            0 <= pct <= 100,
            f"max_drawdown={pct:.1f}%",
        )

    def check_hhi_range(self):
        """HHI should be in [0, 10000]."""
        hhi = self.conc.get("hhi", 0)
        self._check(
            "D7: HHI dans [0, 10000]",
            0 <= hhi <= 10000,
            f"hhi={hhi:.0f}",
        )

    # ── E. STRESS TESTS ──

    def check_stress_test_20(self):
        """Stress -20%: potential_loss = current_value * 0.20."""
        if len(self.stress) < 1:
            self.errors.append("  FAIL  E1: No stress test -20% data")
            return
        st = self.stress[0]
        expected = self.d["total_value"] * 0.20
        self._check(
            "E1: Stress -20% = Patrimoine * 0.20",
            approx_eq(st["potential_loss"], expected, atol=0.05),
            f"expected={expected:.2f}, actual={st['potential_loss']:.2f}",
        )

    def check_stress_test_40(self):
        """Stress -40%: potential_loss = current_value * 0.40."""
        if len(self.stress) < 2:
            self.errors.append("  FAIL  E2: No stress test -40% data")
            return
        st = self.stress[1]
        expected = self.d["total_value"] * 0.40
        self._check(
            "E2: Stress -40% = Patrimoine * 0.40",
            approx_eq(st["potential_loss"], expected, atol=0.05),
            f"expected={expected:.2f}, actual={st['potential_loss']:.2f}",
        )

    # ── G. ALLOCATION ──

    def check_allocation_sum(self):
        """Asset allocation percentages should sum to ~100%."""
        alloc = self.d.get("asset_allocation", [])
        if not alloc:
            self.passes.append("  SKIP  G: Allocation (no data)")
            return
        total_pct = sum(a.get("percentage", 0) for a in alloc)
        self._check(
            "G: Allocation % sums to ~100%",
            approx_eq(total_pct, 100.0, atol=1.0),
            f"sum={total_pct:.1f}%",
        )

    # ── F. HISTORICAL DATA ──

    def check_gain_loss_equals_net_gain(self):
        """Last historical point gain_loss should ≈ net_gain_loss."""
        hist = self.d.get("historical_data", [])
        if not hist:
            self.passes.append("  SKIP  F: Historical gain_loss (no data)")
            return
        last = hist[-1]
        gl = last.get("gain_loss", 0)
        invested = last.get("invested", 0)
        value = last.get("value", 0)
        expected_gl = value - invested
        self._check(
            "F: Dernier point gain_loss = value - invested",
            approx_eq(gl, expected_gl, atol=1.0),
            f"gain_loss={gl:.2f}, value-invested={expected_gl:.2f}",
        )

    # ── GENERAL ──

    def check_no_nan(self):
        """No NaN or Infinity in key metrics."""
        checks = [
            ("total_value", self.d.get("total_value")),
            ("total_invested", self.d.get("total_invested")),
            ("net_gain_loss", self.d.get("net_gain_loss")),
            ("net_gain_loss_percent", self.d.get("net_gain_loss_percent")),
            ("volatility", self.risk.get("volatility")),
            ("sharpe_ratio", self.risk.get("sharpe_ratio")),
            ("roi_annualized", self.adv.get("roi_annualized")),
        ]
        for name, val in checks:
            if val is not None and (math.isnan(val) or math.isinf(val)):
                self.errors.append(f"  FAIL  NaN/Inf: {name}={val}")
                return
        self.passes.append("  PASS  No NaN/Infinity in key metrics")


def get_token() -> str:
    """Get auth token from env or login."""
    if TOKEN:
        return TOKEN

    if not EMAIL or not PASSWORD:
        print("ERROR: Set INVESTAI_TOKEN or (INVESTAI_EMAIL + INVESTAI_PASSWORD)")
        sys.exit(1)

    r = httpx.post(
        f"{API_URL}/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def main():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Fetch dashboard with "Tout" period (days=0)
    print(f"Fetching dashboard from {API_URL}/dashboard?days=0 ...")
    r = httpx.get(f"{API_URL}/dashboard?days=0", headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()

    # Print key values for reference
    print("\n--- Key Values ---")
    print(f"  Patrimoine Total:  {data['total_value']:.2f} EUR")
    print(f"  Total Investi:     {data['total_invested']:.2f} EUR")
    print(f"  Capital Net:       {data['net_capital']:.2f} EUR")
    print(f"  Plus-value Nette:  {data['net_gain_loss']:.2f} EUR ({data['net_gain_loss_percent']:.2f}%)")
    pnl = data.get("advanced_metrics", {}).get("pnl_breakdown", {})
    print(f"  P&L Latent:        {pnl.get('unrealized_pnl', 0):.2f} EUR")
    print(f"  P&L Realise:       {pnl.get('realized_pnl', 0):.2f} EUR")
    print(f"  Total Frais:       {pnl.get('total_fees', 0):.2f} EUR")
    print(f"  P&L Total:         {pnl.get('total_pnl', 0):.2f} EUR")
    print(f"  P&L Net:           {pnl.get('net_pnl', 0):.2f} EUR")
    adv = data.get("advanced_metrics", {})
    print(f"  ROI Annualise:     {adv.get('roi_annualized', 0):.2f}%")
    risk = adv.get("risk_metrics", {})
    print(f"  Volatilite:        {risk.get('volatility', 0):.1f}%")
    print(f"  Sharpe:            {risk.get('sharpe_ratio', 0):.2f}")
    var95 = risk.get("var_95", {})
    print(f"  VaR 95%:           {var95.get('var_amount', 0):.2f} EUR ({var95.get('var_percent', 0):.1f}%)")
    mdd = risk.get("max_drawdown", {})
    print(f"  Max Drawdown:      -{mdd.get('max_drawdown_percent', 0):.1f}%")
    conc = adv.get("concentration", {})
    print(f"  HHI:               {conc.get('hhi', 0):.0f}")
    print(f"  Period Change:     {data.get('period_change', 0):.2f} EUR ({data.get('period_change_percent', 0):.2f}%)")

    # Run verification
    verifier = DashboardVerifier(data)
    ok = verifier.run_all()

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
