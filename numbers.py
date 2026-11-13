"""
Number helpers.

    - split_evenly: divide a decimal total into equal parts with a fixed
      precision (e.g. cents), giving the leftover steps to the first parts,
      so the parts always add up exactly to the total.
"""

from decimal import ROUND_DOWN, Decimal

# Default precision of split_evenly: cents.
CENT = Decimal("0.01")


def split_evenly(total: Decimal, parts: int, step: Decimal = CENT) -> list[Decimal]:
    """
    Divide a total into equal parts that add up exactly to it.

    Every part is total / parts rounded down to `step`; the steps left
    over go one each to the first parts, so the caller decides who gets
    them by ordering its items. Example: 100 into 3 -> [33.34, 33.33, 33.33].

    Args:
        total: the amount to divide, a multiple of `step`.
        parts: number of parts, >= 1.
        step: precision of the parts (Decimal("0.01") = cents).

    Returns:
        `parts` values whose sum is `total`, the largest first.

    Raises:
        ValueError: parts < 1, or total not a multiple of step (the parts
            could not add up to it exactly).
    """
    if parts < 1:
        raise ValueError(f"parts must be at least 1, got {parts}")
    if total % step != 0:
        raise ValueError(f"total {total} is not a multiple of step {step}")
    base = (total / parts).quantize(step, rounding=ROUND_DOWN)
    leftover = int((total - base * parts) / step)
    return [base + step if index < leftover else base for index in range(parts)]
