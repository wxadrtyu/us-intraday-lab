from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetQuality(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    duplicate_rows: int = Field(default=0, ge=0)
    missing_expected_bars: int = Field(default=0, ge=0)
    invalid_ohlc_rows: int = Field(default=0, ge=0)
    invalid_volume_rows: int = Field(default=0, ge=0)
    outside_session_rows: int = Field(default=0, ge=0)
    non_monotonic_groups: int = Field(default=0, ge=0)


class DatasetManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str = Field(min_length=1)
    schema_version: str
    source_uri: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_revision: str
    calendar_name: str
    calendar_version: str
    created_at: datetime
    provider: str
    feed: str
    bar_size: str
    row_count: int = Field(ge=0)
    symbols: tuple[str, ...]
    min_timestamp: datetime
    max_timestamp: datetime
    quality: DatasetQuality

    @model_validator(mode="after")
    def validate_range(self) -> "DatasetManifest":
        if self.min_timestamp > self.max_timestamp:
            raise ValueError("min_timestamp must not exceed max_timestamp")
        return self
