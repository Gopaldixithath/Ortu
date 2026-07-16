from __future__ import annotations

from datetime import datetime, timedelta, timezone


class FitnessRuleError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_capacity(*, capacity: int, confirmed_count: int) -> None:
    if capacity < 1:
        raise FitnessRuleError("This class is not open for booking.")
    if confirmed_count >= capacity:
        raise FitnessRuleError("This class is full. Please choose another session.")


def ensure_booking_window(*, starts_at: datetime, now: datetime | None = None) -> None:
    current = now or utc_now()
    if starts_at <= current:
        raise FitnessRuleError("This class has already started.")


def ensure_cancellable(*, starts_at: datetime, now: datetime | None = None, cutoff_minutes: int = 60) -> None:
    current = now or utc_now()
    if starts_at - current < timedelta(minutes=cutoff_minutes):
        raise FitnessRuleError("Online cancellation closes 1 hour before the class starts.")


def ensure_membership_can_book(
    *,
    status: str,
    starts_at: datetime | None,
    ends_at: datetime | None,
    remaining_classes: int | None,
    class_start: datetime,
) -> None:
    if status != "active":
        raise FitnessRuleError("Your membership is not active yet.")
    if starts_at and class_start < starts_at:
        raise FitnessRuleError("This class is before your membership starts.")
    if ends_at and class_start >= ends_at:
        raise FitnessRuleError("This class is outside your membership period.")
    if remaining_classes is not None and remaining_classes < 1:
        raise FitnessRuleError("You have used all class credits in this membership.")
