"""
Number helpers.

    - split_evenly: divide a decimal total into equal parts with a fixed
      precision (e.g. cents), giving the leftover steps to the first parts,
      so the parts always add up exactly to the total.
    - split_by_weights: the same, in proportion to weights (largest
      remainder method).
    - minimal_transfers: the fewest transfers that bring a set of balances
      (adding up to zero) to zero.
"""

from collections.abc import Hashable, Mapping, Sequence
from decimal import ROUND_DOWN, Decimal
from typing import TypeVar

# Key of a balance in minimal_transfers (any hashable value).
K = TypeVar("K", bound=Hashable)

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


def split_by_weights(total: Decimal, weights: Sequence[Decimal], step: Decimal = CENT) -> list[Decimal]:
    """
    Divide a total in proportion to weights, with parts that add up exactly
    to it (largest remainder method).

    Every part is total * weight / sum(weights) rounded towards zero to
    `step`; the steps left over go one each to the parts with the largest
    discarded remainder (ties: the first ones). Example: 100 by [1, 1, 1]
    -> [33.34, 33.33, 33.33]; -10 by [50, 50] -> [-5, -5].

    Args:
        total: the amount to divide (also negative), a multiple of `step`.
        weights: one weight per part, each >= 0, not all 0.
        step: precision of the parts.

    Returns:
        One value per weight, in the same order, adding up to `total`.

    Raises:
        ValueError: no weights, a negative weight, all weights 0, or total
            not a multiple of step.
    """
    if not weights or any(w < 0 for w in weights) or sum(weights) == 0:
        raise ValueError(f"weights must be >= 0 and not all 0: {list(weights)}")
    if total % step != 0:
        raise ValueError(f"total {total} is not a multiple of step {step}")
    sign = -1 if total < 0 else 1
    amount = abs(total)
    weight_sum = sum(weights)
    exact = [amount * w / weight_sum for w in weights]
    parts = [e.quantize(step, rounding=ROUND_DOWN) for e in exact]
    leftover = int((amount - sum(parts)) / step)
    by_remainder = sorted(range(len(parts)), key=lambda i: (-(exact[i] - parts[i]), i))
    for index in by_remainder[:leftover]:
        parts[index] += step
    return [sign * p for p in parts]


# Largest number of non-zero balances minimal_transfers solves exactly; above
# it uses the greedy pairing, at most one transfer more per extra balance.
EXACT_TRANSFERS_LIMIT = 12


def minimal_transfers(balances: Mapping[K, Decimal]) -> list[tuple[K, K, Decimal]]:
    """
    Transfers that bring a set of balances to zero, in the smallest number
    of steps: who must give money pays who must receive it (e.g. the
    settlement of shared expenses among friends).

    The minimum is n - g, where n is the number of non-zero balances and g
    the largest number of disjoint groups adding up to zero; every group is
    then settled by pairing its largest debtor with its largest creditor.
    Exact up to EXACT_TRANSFERS_LIMIT non-zero balances, greedy above.

    Args:
        balances: key -> balance; > 0 must receive, < 0 must give. Keys are
            any hashable values; ties are broken by the mapping order.

    Returns:
        (payer, payee, amount) triples with amount > 0, whose effect brings
        every balance to zero.

    Raises:
        ValueError: the balances do not add up to zero.
    """
    if sum(balances.values(), start=Decimal(0)) != 0:
        raise ValueError(f"balances must add up to zero: {dict(balances)}")
    keys = [k for k, v in balances.items() if v != 0]
    groups = _zero_sum_groups(keys, balances) if len(keys) <= EXACT_TRANSFERS_LIMIT else [keys]
    transfers = []
    for group in groups:
        transfers += _greedy_transfers({k: balances[k] for k in group})
    return transfers


def _zero_sum_groups(keys: list, balances: Mapping) -> list[list]:
    """
    Split keys into the largest number of disjoint groups whose balances add
    up to zero (dynamic programming over subsets).

    Args:
        keys: the keys with a non-zero balance (at most EXACT_TRANSFERS_LIMIT).
        balances: key -> balance, adding up to zero over `keys`.

    Returns:
        The groups, each a list of keys in the order of `keys`.
    """
    n = len(keys)
    full = (1 << n) - 1
    sums = [Decimal(0)] * (1 << n)
    for mask in range(1, 1 << n):
        low = (mask & -mask).bit_length() - 1
        sums[mask] = sums[mask & (mask - 1)] + balances[keys[low]]
    # best[mask] = most zero-sum groups that a set of keys `mask` (adding up
    # to zero) can be split into; cut[mask] = the first group of that split.
    best = [0] * (1 << n)
    cut = [0] * (1 << n)
    for mask in range(1, 1 << n):
        if sums[mask] != 0:
            continue
        best[mask], cut[mask] = 1, mask
        sub = (mask - 1) & mask
        while sub:
            if sums[sub] == 0 and best[sub] == 1 and best[mask ^ sub] + 1 > best[mask]:
                best[mask], cut[mask] = best[mask ^ sub] + 1, sub
            sub = (sub - 1) & mask
    groups, mask = [], full
    while mask:
        groups.append([keys[i] for i in range(n) if cut[mask] >> i & 1])
        mask ^= cut[mask]
    return groups


def _greedy_transfers(balances: dict) -> list[tuple]:
    """
    Settle balances adding up to zero by repeatedly pairing the largest
    debtor with the largest creditor (at most len(balances) - 1 transfers).

    Args:
        balances: key -> non-zero balance, adding up to zero.

    Returns:
        (payer, payee, amount) triples.
    """
    order = {k: i for i, k in enumerate(balances)}
    left = dict(balances)
    transfers = []
    while any(left.values()):
        payer = min(left, key=lambda k: (left[k], order[k]))
        payee = max(left, key=lambda k: (left[k], -order[k]))
        amount = min(-left[payer], left[payee])
        transfers.append((payer, payee, amount))
        left[payer] += amount
        left[payee] -= amount
    return transfers
