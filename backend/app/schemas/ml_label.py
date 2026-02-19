from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ActivityQualityLabelUpsertIn(BaseModel):
    label_bad: bool
    label_source: str = Field(min_length=1, max_length=32)
    label_reason: str | None = None
    label_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    label_version: int = Field(default=1, ge=1)
    created_by: str | None = Field(default=None, max_length=128)


class ActivityQualityLabelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activity_id: int
    label_bad: bool
    label_source: str
    label_reason: str | None
    label_confidence: float | None
    label_version: int
    created_at: datetime
    created_by: str | None
