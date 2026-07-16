"""Seed a realistic starter timetable for ORTU Fitness.

Idempotent: does nothing if any future scheduled classes already exist.
Run it once after the first deploy so the timetable is not empty:

    docker compose exec web python seed.py
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import FitnessClassSession

BUSINESS_KEY = "ortu-fitness"


def _at(day_offset: int, hour: int, minute: int = 0) -> datetime:
    base = datetime.now(timezone.utc).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base + timedelta(days=day_offset)


# name, coach, capacity, day_offset, hour, duration_min, description
PLAN = [
    ("Strength & Conditioning", "Coach Maya", 12, 0, 18, 60, "Full-body strength with progressive loading. All levels welcome."),
    ("Sunrise HIIT", "Coach Leo", 14, 1, 7, 45, "High-intensity intervals to kick-start your day."),
    ("Mobility & Flow", "Coach Priya", 10, 1, 18, 60, "Controlled movement, breath and deep mobility work."),
    ("Kettlebell Power", "Coach Sam", 10, 2, 19, 45, "Swing, clean and press — build explosive power."),
    ("Small-Group Barbell", "Coach Maya", 8, 3, 18, 60, "Coached barbell technique in a small group."),
    ("Saturday Sweat", "Coach Leo", 16, 4, 9, 50, "Weekend conditioning circuit for every fitness level."),
    ("Core & Stability", "Coach Priya", 12, 5, 10, 45, "Targeted core, balance and stability training."),
    ("Sunday Reset", "Coach Sam", 12, 6, 10, 60, "Low-impact strength and stretch to close the week."),
]


def main() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        existing = (
            db.query(FitnessClassSession)
            .filter(
                FitnessClassSession.business_key == BUSINESS_KEY,
                FitnessClassSession.start_at >= now,
                FitnessClassSession.status == "scheduled",
            )
            .count()
        )
        if existing:
            print(f"SKIP: {existing} future scheduled classes already exist.")
            return
        created = 0
        for name, coach, cap, day, hour, dur, desc in PLAN:
            start = _at(day, hour)
            if start <= now:
                start += timedelta(days=7)
            db.add(
                FitnessClassSession(
                    business_key=BUSINESS_KEY,
                    name=name,
                    description=desc,
                    coach_name=coach,
                    location="ORTU Fitness Studio",
                    start_at=start,
                    end_at=start + timedelta(minutes=dur),
                    capacity=cap,
                    status="scheduled",
                )
            )
            created += 1
        db.commit()
        print(f"CREATED {created} starter classes.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
