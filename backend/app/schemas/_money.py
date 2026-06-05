"""Shared ``Money`` annotated type for API schemas.

Pydantic v2 serializes ``Decimal`` to a JSON **string** by default (``"1000.50"``
instead of ``1000.50``). The frontend types those fields as ``number`` and uses
methods like ``toFixed`` / ``toLocaleString`` on them — which crash when fed a
string. JavaScript coerces strings in arithmetic so the bug is silent until a
formatter touches the value.

Using ``Money`` instead of ``Decimal`` in schema annotations keeps the rich
``Decimal`` validation on incoming requests but forces JSON serialization to
``float`` on responses. The change is transparent for Python code: ``Money`` is
``Decimal`` at runtime.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Optional

from pydantic import PlainSerializer


def _to_float(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    return float(value)


# Use ``when_used="json-unless-none"`` so that:
#  - ``None`` stays ``null`` in JSON (the alternative would coerce to ``0.0``).
#  - Python-side ``model_dump()`` still returns a ``Decimal`` for downstream
#    code that does precise math on the dumped value.
Money = Annotated[
    Decimal,
    PlainSerializer(_to_float, return_type=float, when_used="json-unless-none"),
]
