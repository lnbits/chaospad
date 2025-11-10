empty_dict: dict[str, str] = {}


async def m001_pads(db):
    """
    Initial pads table.
    """

    await db.execute(
        f"""
        CREATE TABLE chaospad.pads (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            updated_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
    """
    )


async def m002_snapshots(db):
    """
    Yjs snapshot storage.
    - Postgres: use schema table chaospad.snapshots
    - SQLite : use plain table name snapshots
    """
    is_pg = getattr(db, "type", "").upper() == "POSTGRES"
    blob_type = "BYTEA" if is_pg else "BLOB"
    tbl = "chaospad.snapshots" if is_pg else "snapshots"
    await db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {tbl} (
            id TEXT PRIMARY KEY,
            pads_id TEXT NOT NULL,
            update_blob {blob_type} NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
        """
    )
    await db.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_chaospad_snapshots_pads_time
        ON {tbl} (pads_id, created_at);
        """
    )
