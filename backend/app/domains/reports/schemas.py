from pydantic import BaseModel, Field, field_validator

_CRYPTO_CLASSES = {"L1", "L2", "DeFi", "Stable", "Meme", "Other"}


class RebalancingRequest(BaseModel):
    """Request body for rebalancing report."""

    target_allocations: dict[str, float] = Field(
        ...,
        description=(
            "Target allocation per crypto class. Keys: L1, L2, DeFi, Stable, Meme, Other. Values: 0.0–1.0."  # noqa: RUF001
        ),
        examples=[{"L1": 0.50, "Stable": 0.20, "DeFi": 0.20, "Meme": 0.10}],
    )

    @field_validator("target_allocations")
    @classmethod
    def validate_allocations(cls, v: dict[str, float]) -> dict[str, float]:
        """Clés parmi les six classes crypto, poids entre 0 et 1, somme à 1 (± 0,01)."""
        for key in v:
            if key not in _CRYPTO_CLASSES:
                raise ValueError(f"Invalid category '{key}'. Allowed: {_CRYPTO_CLASSES}")
        total = sum(v.values())
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Allocations must sum to 1.0 (got {total:.4f})")
        for key, val in v.items():
            if val < 0 or val > 1:
                raise ValueError(f"Allocation for '{key}' must be between 0 and 1")
        return v
