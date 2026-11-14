"""
Deadline registry: one place where every kind of deadline of a project is
collected (payments due, renewals, expirations...), for a calendar page and
for notifications.

A project registers one provider per kind of deadline; a provider returns
the deadlines a user can see in a period. collect() merges every provider,
so a new kind (e.g. "yearly renewal of a contract") is added by registering
one more provider, without touching the callers:

    registry = DeadlineRegistry()

    @registry.provider("invoice_due")
    def invoices_due(user, start, end):
        return [Deadline("invoice_due", i.due_date, "invoice", i.pk, amount=i.total)
                for i in Invoice.objects.accessible_by(user).filter(due_date__range=(start, end))]

    registry.collect(user, date(2026, 6, 1), date(2026, 6, 30))

Reminders and notifications should read the same registry, so a calendar
and the reminders never disagree.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

# A provider: (user, start, end) -> deadlines with start <= due_date <= end.
Provider = Callable[[object, date, date], Iterable["Deadline"]]


@dataclass(frozen=True)
class Deadline:
    """
    One deadline, as plain data.

    Fields:
        kind      -> code of the kind of deadline (English, the program
                     compares it; the project labels it for the user).
        due_date  -> when it falls.
        subject   -> code of what it is about (e.g. "tax", "lease").
        subject_id -> primary key of that object.
        amount    -> money involved, if any.
        context   -> extra JSON-serializable data for the interface (ids
                     of related objects, a label...).
    """

    kind: str
    due_date: date
    subject: str
    subject_id: int
    amount: Decimal | None = None
    context: dict = field(default_factory=dict)


class DeadlineRegistry:
    """Providers of deadlines by kind, and their merged result."""

    def __init__(self):
        self._providers: dict[str, Provider] = {}

    def provider(self, kind: str) -> Callable[[Provider], Provider]:
        """
        Decorator registering the provider of one kind of deadline.

        Args:
            kind: the code of the kind, unique in the registry.

        Returns:
            The decorator (it returns the function unchanged).

        Raises:
            ValueError: a provider for that kind is already registered.
        """

        def register(function: Provider) -> Provider:
            if kind in self._providers:
                raise ValueError(f"Deadline kind {kind!r} already has a provider")
            self._providers[kind] = function
            return function

        return register

    def kinds(self) -> list[str]:
        """The registered kinds, sorted."""
        return sorted(self._providers)

    def collect(self, user, start: date, end: date, kinds: Iterable[str] | None = None) -> list[Deadline]:
        """
        Every deadline the user can see in a period.

        Args:
            user: the user (providers apply their own access rules).
            start, end: the period, both included.
            kinds: only these kinds; None for all.

        Returns:
            The deadlines by date, then kind and subject id.

        Raises:
            ValueError: end before start, or an unknown kind.
            ValueError: a provider returned a deadline of another kind or
                outside the period (a bug of the provider).
        """
        if end < start:
            raise ValueError("end must not be before start")
        wanted = self.kinds() if kinds is None else list(kinds)
        unknown = set(wanted) - set(self._providers)
        if unknown:
            raise ValueError(f"Unknown deadline kinds: {sorted(unknown)}")
        found = []
        for kind in wanted:
            for deadline in self._providers[kind](user, start, end):
                if deadline.kind != kind or not start <= deadline.due_date <= end:
                    raise ValueError(f"Provider of {kind!r} returned {deadline!r}")
                found.append(deadline)
        return sorted(found, key=lambda d: (d.due_date, d.kind, d.subject_id))
