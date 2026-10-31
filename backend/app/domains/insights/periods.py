"""Mois couverts par une série mensuelle."""


def covered_months(observed: list[str]) -> int:
    """Mois du premier au dernier observé, inclus ; une clé hors format AAAA-MM ne situe rien et reste ignorée."""
    valid = sorted(month for month in observed if len(month) == 7 and month[4] == "-")
    if not valid:
        return 1
    first, last = valid[0], valid[-1]
    gap = (int(last[:4]) - int(first[:4])) * 12 + (int(last[5:]) - int(first[5:]))
    return max(gap + 1, 1)
