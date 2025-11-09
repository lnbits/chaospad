from lnbits.db import Database, Filters, Page
from lnbits.helpers import urlsafe_short_hash

from .models import (
    CreatePads,
    Pads,
    PadsFilters,
)

db = Database("ext_chaospad")


########################### Pads ############################
async def create_pads(user_id: str, data: CreatePads) -> Pads:
    pads = Pads(**data.dict(), id=urlsafe_short_hash(), user_id=user_id)
    await db.insert("chaospad.pads", pads)
    return pads


async def get_pads(
    user_id: str,
    pads_id: str,
) -> Pads | None:
    return await db.fetchone(
        """
            SELECT * FROM chaospad.pads
            WHERE id = :id AND user_id = :user_id
        """,
        {"id": pads_id, "user_id": user_id},
        Pads,
    )


async def get_pads_by_id(
    pads_id: str,
) -> Pads | None:
    return await db.fetchone(
        """
            SELECT * FROM chaospad.pads
            WHERE id = :id
        """,
        {"id": pads_id},
        Pads,
    )


async def get_pads_ids_by_user(
    user_id: str,
) -> list[str]:
    rows: list[dict] = await db.fetchall(
        """
            SELECT DISTINCT id FROM chaospad.pads
            WHERE user_id = :user_id
        """,
        {"user_id": user_id},
    )

    return [row["id"] for row in rows]


async def get_pads_paginated(
    user_id: str | None = None,
    filters: Filters[PadsFilters] | None = None,
) -> Page[Pads]:
    where = []
    values = {}
    if user_id:
        where.append("user_id = :user_id")
        values["user_id"] = user_id

    return await db.fetch_page(
        "SELECT * FROM chaospad.pads",
        where=where,
        values=values,
        filters=filters,
        model=Pads,
    )


async def update_pads(data: Pads) -> Pads:
    await db.update("chaospad.pads", data)
    return data


async def delete_pads(user_id: str, pads_id: str) -> None:
    await db.execute(
        """
            DELETE FROM chaospad.pads
            WHERE id = :id AND user_id = :user_id
        """,
        {"id": pads_id, "user_id": user_id},
    )


######################### Snapshots ############################


async def create_snapshot(pads_id: str, update_blob: bytes) -> None:
    await db.execute(
        """
        INSERT INTO chaospad.snapshots (id, pads_id, update_blob, created_at)
        VALUES (:id, :pads_id, :update_blob, CURRENT_TIMESTAMP)
        """,
        {
            "id": urlsafe_short_hash(),
            "pads_id": pads_id,
            "update_blob": update_blob,
        },
    )


async def get_latest_snapshot(pads_id: str) -> bytes | None:
    row = await db.fetchone(
        """
        SELECT update_blob
        FROM chaospad.snapshots
        WHERE pads_id = :pads_id
        ORDER BY created_at DESC
        LIMIT 1
        """,
        {"pads_id": pads_id},
    )
    return row["update_blob"] if row else None


async def prune_old_snapshots(pads_id: str, keep: int = 20) -> None:
    await db.execute(
        """
        WITH old AS (
          SELECT id
          FROM chaospad.snapshots
          WHERE pads_id = :pads_id
          ORDER BY created_at DESC
          LIMIT -1 OFFSET :keep
        )
        DELETE FROM chaospad.snapshots
        WHERE id IN (SELECT id FROM old)
        """,
        {"pads_id": pads_id, "keep": keep},
    )
