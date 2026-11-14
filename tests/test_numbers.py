"""
Tests for djkit.numbers.

Run with: python manage.py test djkit.tests.test_numbers
"""

from decimal import Decimal

from django.test import SimpleTestCase

from djkit.numbers import minimal_transfers, split_by_weights, split_evenly


class SplitEvenlyTests(SimpleTestCase):
    """split_evenly divides a total into equal parts adding up exactly to it."""

    def test_exact_division(self):
        """50.00 into 2 -> [25.00, 25.00]."""
        self.assertEqual(split_evenly(Decimal("50.00"), 2), [Decimal("25.00"), Decimal("25.00")])

    def test_leftover_cents_go_to_the_first_parts(self):
        """100 into 3 -> [33.34, 33.33, 33.33]; 0.05 into 3 -> [0.02, 0.02, 0.01]."""
        self.assertEqual(split_evenly(Decimal("100"), 3), [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")])
        self.assertEqual(split_evenly(Decimal("0.05"), 3), [Decimal("0.02"), Decimal("0.02"), Decimal("0.01")])

    def test_parts_always_add_up_to_the_total(self):
        """Totals 0.01 to 1.00 into 1 to 7 parts: the sum is always the total."""
        for cents in range(1, 101):
            total = Decimal(cents) / 100
            for parts in range(1, 8):
                with self.subTest(total=total, parts=parts):
                    self.assertEqual(sum(split_evenly(total, parts)), total)

    def test_custom_step(self):
        """10 into 3 with step 1 -> [4, 3, 3]."""
        self.assertEqual(split_evenly(Decimal("10"), 3, step=Decimal("1")), [4, 3, 3])

    def test_invalid_arguments(self):
        """0 parts, or a total with more decimals than the step -> ValueError."""
        with self.assertRaises(ValueError):
            split_evenly(Decimal("10"), 0)
        with self.assertRaises(ValueError):
            split_evenly(Decimal("10.005"), 2)


class SplitByWeightsTests(SimpleTestCase):
    """split_by_weights: proportional parts that add up exactly to the total."""

    def test_parts_add_up_with_the_largest_remainders(self):
        """100 by [1, 1, 1] -> 33.34, 33.33, 33.33; 10 by [33.33, 33.33, 33.34] adds up to 10."""
        self.assertEqual(split_by_weights(Decimal("100"), [Decimal(1)] * 3), [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")])
        parts = split_by_weights(Decimal("10"), [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")])
        self.assertEqual(sum(parts), Decimal("10"))

    def test_negative_total_and_zero_weights(self):
        """-10 by [50, 50, 0] -> -5, -5, 0."""
        self.assertEqual(split_by_weights(Decimal("-10"), [Decimal(50), Decimal(50), Decimal(0)]), [Decimal(-5), Decimal(-5), Decimal(0)])

    def test_invalid_input_is_a_bug(self):
        """No weights, all zero, negative weight, total not in cents -> ValueError."""
        for total, weights in ((Decimal(1), []), (Decimal(1), [Decimal(0)]), (Decimal(1), [Decimal(-1), Decimal(2)]), (Decimal("0.001"), [Decimal(1)])):
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                split_by_weights(total, weights)


def apply(balances: dict, transfers: list) -> dict:
    """The balances after the transfers (payer receives back what they owe)."""
    left = dict(balances)
    for payer, payee, amount in transfers:
        left[payer] += amount
        left[payee] -= amount
    return left


class MinimalTransfersTests(SimpleTestCase):
    """minimal_transfers: the fewest transfers that bring balances to zero."""

    def test_two_people(self):
        """a -700, b +700 -> a pays b 700."""
        self.assertEqual(minimal_transfers({"a": Decimal(-700), "b": Decimal(700)}), [("a", "b", Decimal(700))])

    def test_zero_balances_need_no_transfer(self):
        """Everyone at 0 -> no transfers."""
        self.assertEqual(minimal_transfers({"a": Decimal(0), "b": Decimal(0)}), [])

    def test_zero_sum_groups_save_transfers(self):
        """a -5, b +5, c -7, d +7: 2 transfers (a->b, c->d), where a greedy pairing could need 3."""
        balances = {"c": Decimal(-7), "a": Decimal(-5), "b": Decimal(5), "d": Decimal(7)}
        transfers = minimal_transfers(balances)
        self.assertEqual(len(transfers), 2)
        self.assertEqual(set(apply(balances, transfers).values()), {Decimal(0)})

    def test_greedy_case_reaches_zero(self):
        """-300, -100, +250, +150: 3 transfers, every balance back to 0."""
        balances = {"a": Decimal(-300), "b": Decimal(-100), "c": Decimal(250), "d": Decimal(150)}
        transfers = minimal_transfers(balances)
        self.assertEqual(len(transfers), 3)
        self.assertTrue(all(amount > 0 for _, _, amount in transfers))
        self.assertEqual(set(apply(balances, transfers).values()), {Decimal(0)})

    def test_balances_not_adding_up_to_zero_are_a_bug(self):
        """a -1, b +2 -> ValueError."""
        with self.assertRaises(ValueError):
            minimal_transfers({"a": Decimal(-1), "b": Decimal(2)})
