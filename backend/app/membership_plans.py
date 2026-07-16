from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class FitnessPlan:
    slug: str
    name: str
    price_pence: int
    billing_kind: str
    description: str
    included_classes: Optional[int] = None
    duration_days: Optional[int] = None
    interval_unit: Optional[str] = None
    featured: bool = False

    def public_dict(self) -> dict:
        value = asdict(self)
        value["price"] = f"£{self.price_pence / 100:.0f}"
        return value


ORTU_PLANS = (
    FitnessPlan("payg", "Single class", 700, "one_off", "One flexible class credit.", included_classes=1, duration_days=30),
    FitnessPlan("14-day-pass", "14-day pass", 2200, "one_off", "Unlimited classes for 14 consecutive days.", duration_days=14),
    FitnessPlan("28-day-pass", "28-day pass", 4200, "one_off", "Unlimited classes for 28 consecutive days.", duration_days=28),
    FitnessPlan("four-monthly", "4 classes monthly", 2500, "recurring", "Four class credits renewed every month.", included_classes=4, duration_days=31, interval_unit="monthly"),
    FitnessPlan("eight-monthly", "8 classes monthly", 3500, "recurring", "Eight class credits renewed every month.", included_classes=8, duration_days=31, interval_unit="monthly"),
    FitnessPlan("unlimited-monthly", "Unlimited monthly", 4000, "recurring", "Unlimited classes with a monthly Direct Debit.", duration_days=31, interval_unit="monthly", featured=True),
)

PLAN_BY_SLUG = {plan.slug: plan for plan in ORTU_PLANS}
