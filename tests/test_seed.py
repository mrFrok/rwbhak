"""Сид должен переживать повторный `--reset`, когда id рейсов уже не 1/2/3.

В PostgreSQL последовательности не сбрасываются вместе с DELETE: после нескольких
запусков новые рейсы получают id 4, 5, 6 и дальше. Сид не должен зависеть от id.
"""

from sqlalchemy import select

from api.db import Base, SessionLocal, engine
from api.models import Trip
from data.seed import seed


def test_seed_survives_repeated_reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db, reset=True)
        seed(db, reset=True)
        trips = db.scalars(select(Trip)).all()
        assert len(trips) == 3
        composition = sorted(len(trip.orders) for trip in trips)
        assert composition == [13, 30, 99]
        kinds = sorted(trip.kind for trip in trips)
        assert kinds == ["ALONG", "DEDICATED", "DEDICATED"]
    Base.metadata.drop_all(engine)
