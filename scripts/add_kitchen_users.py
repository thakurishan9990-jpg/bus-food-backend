"""Add the DL-234 kitchen staff accounts, and nothing else.

A one-off, narrower alternative to scripts/seed.py for databases that are
already seeded: it adds only the four dhaba users below (the same entries as in
data/dhabago_seed.json) and never touches admins, passengers or any other row.

Idempotent and hands-off: each user is inserted with ON CONFLICT (phone) DO
NOTHING, so a phone that already exists is skipped by the database without this
script reading or changing that row: no password resets, no role changes,
whatever role the existing account has. The only table read is dhabas, to
resolve the slugs, and every slug is checked before anything is written.

Usage:
    python -m scripts.add_kitchen_users
"""
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.dhaba import Dhaba
from app.models.user import User, UserRole
from app.utils.auth import hash_password

PASSWORD = "dhaba123"
KITCHEN_USERS = [
    # (phone, name, dhaba slug)
    ("9876500002", "Hari Om staff", "ddn-hari-om-highway-plaza"),
    ("9876500003", "Gur Mandi staff", "ddn-gur-mandi-dhaba"),
    ("9876500004", "Chai Corner staff", "ddn-highway-chai-corner"),
    ("9876500005", "Shivalik staff", "ddn-shivalik-dhaba"),
]


def _insert_if_new_phone(db: Session):
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        return lambda values: pg_insert(User).values(**values).on_conflict_do_nothing(index_elements=["phone"])
    if dialect == "sqlite":
        return lambda values: sqlite_insert(User).values(**values).on_conflict_do_nothing(index_elements=["phone"])
    raise RuntimeError(f"Unsupported database dialect {dialect!r}")


def add_kitchen_users(db: Session) -> tuple[list[str], list[str]]:
    """Insert the kitchen users whose phone isn't taken. Returns (created, skipped) summary lines."""
    slugs = [slug for _, _, slug in KITCHEN_USERS]
    dhaba_ids = dict(db.query(Dhaba.slug, Dhaba.id).filter(Dhaba.slug.in_(slugs)).all())
    missing = [slug for slug in slugs if slug not in dhaba_ids]
    if missing:
        raise SystemExit(f"No dhaba with slug {', '.join(missing)}; nothing was written.")

    insert_stmt = _insert_if_new_phone(db)
    created, skipped = [], []
    for phone, name, slug in KITCHEN_USERS:
        result = db.execute(insert_stmt({
            "phone": phone,
            "name": name,
            "hashed_password": hash_password(PASSWORD),
            "role": UserRole.DHABA,
            "dhaba_id": dhaba_ids[slug],
        }))
        line = f"{phone}  {name}  -> {slug} (dhaba_id {dhaba_ids[slug]})"
        (created if result.rowcount == 1 else skipped).append(line)
    db.commit()
    return created, skipped


def main() -> None:
    with SessionLocal() as db:
        created, skipped = add_kitchen_users(db)
    print(f"Created {len(created)}:")
    for line in created:
        print(f"  {line}")
    print(f"Skipped {len(skipped)} (phone already exists, left untouched):")
    for line in skipped:
        print(f"  {line}")


if __name__ == "__main__":
    main()
