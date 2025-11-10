from base64 import b64encode
from datetime import datetime, timezone

from lnbits.db import FilterModel
from pydantic import BaseModel, Field, validator

########################### Pads ############################
class CreatePads(BaseModel):
    name: str

class Pads(BaseModel):
    id: str
    user_id: str
    name: str

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PadsFilters(FilterModel):
    __search_fields__ = ["name"]
    __sort_fields__ = ["name", "created_at", "updated_at"]

    created_at: datetime | None
    updated_at: datetime | None


class SnapshotResponse(BaseModel):
    exists: bool
    update_blob: str | None = None  # base64

    @classmethod
    def from_bytes(cls, blob: bytes | None) -> "SnapshotResponse":
        if not blob:
            return cls(exists=False, update_blob=None)
        # Encode bytes → base64 string
        return cls(exists=True, update_blob=b64encode(blob).decode("ascii"))


class SnapshotWriteResult(BaseModel):
    ok: bool = True
    final: bool = False
    rate_limited: bool = False
