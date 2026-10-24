import pytest
from sqlalchemy import event

from app.models.dhaba import Dhaba
from app.models.user import User, UserRole
from app.utils.auth import hash_password, verify_password
from scripts.add_kitchen_users import KITCHEN_USERS, add_kitchen_users

PHONES = [phone for phone, _, _ in KITCHEN_USERS]


@pytest.fixture()
def db(seeded_session):
    """The seeded DB minus the four kitchen users, as on a database seeded before they existed."""
    seeded_session.query(User).filter(User.phone.in_(PHONES)).delete(synchronize_session=False)
    seeded_session.commit()
    return seeded_session


def _snapshot(db):
    return sorted(
        (u.phone, u.name, u.role, u.dhaba_id, u.hashed_password) for u in db.query(User).all()
    )


def test_creates_the_four_kitchen_users_bound_by_slug(db):
    created, skipped = add_kitchen_users(db)

    assert len(created) == 4 and skipped == []
    for phone, name, slug in KITCHEN_USERS:
        user = db.query(User).filter(User.phone == phone).one()
        assert (user.name, user.role, user.dhaba.slug) == (name, UserRole.DHABA, slug)
        assert verify_password("dhaba123", user.hashed_password)


def test_second_run_skips_everything_and_changes_nothing(db):
    add_kitchen_users(db)
    before = _snapshot(db)

    created, skipped = add_kitchen_users(db)

    assert created == [] and len(skipped) == 4
    assert _snapshot(db) == before  # same hashes too: no password resets


def test_existing_phone_is_left_alone_whatever_its_role(db):
    other_dhaba = db.query(Dhaba).filter(Dhaba.slug == "ddn-punjabi-rasoi").one()
    db.add(User(phone="9876500003", name="Someone else", role=UserRole.PASSENGER,
                hashed_password=hash_password("their-own-pw")))
    db.add(User(phone="9876500004", name="Moved staff", role=UserRole.DHABA, dhaba_id=other_dhaba.id,
                hashed_password=hash_password("their-own-pw")))
    db.commit()
    others_before = [row for row in _snapshot(db) if row[0] not in ("9876500002", "9876500005")]

    created, skipped = add_kitchen_users(db)

    assert [line.split()[0] for line in created] == ["9876500002", "9876500005"]
    assert [line.split()[0] for line in skipped] == ["9876500003", "9876500004"]
    others_after = [row for row in _snapshot(db) if row[0] not in ("9876500002", "9876500005")]
    assert others_after == others_before
    assert verify_password("their-own-pw", db.query(User).filter(User.phone == "9876500003").one().hashed_password)


def test_never_reads_users_and_only_inserts_into_them(db):
    statements = []
    engine = db.get_bind()
    listener = lambda conn, cursor, sql, params, context, many: statements.append(sql.lower())
    event.listen(engine, "before_cursor_execute", listener)
    try:
        add_kitchen_users(db)
        add_kitchen_users(db)
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    touching_users = [s for s in statements if "users" in s]
    assert touching_users and all(s.lstrip().startswith("insert into users") for s in touching_users)
    assert all("on conflict (phone) do nothing" in s for s in touching_users)


def test_unknown_slug_writes_nothing(db, monkeypatch):
    monkeypatch.setattr(
        "scripts.add_kitchen_users.KITCHEN_USERS",
        KITCHEN_USERS[:1] + [("9876500099", "Ghost staff", "ddn-no-such-dhaba")],
    )
    before = _snapshot(db)

    with pytest.raises(SystemExit, match="ddn-no-such-dhaba"):
        add_kitchen_users(db)

    assert _snapshot(db) == before
