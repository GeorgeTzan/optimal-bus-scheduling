"""Only correction intent crosses the API boundary; tenant/actor/plan never do."""

from typing import Annotated, Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictFloat,
    StrictStr,
    model_validator,
)

Positive = Annotated[int, Field(strict=True, ge=1)]
Scalar = StrictStr | StrictBool | StrictInt | StrictFloat | None


class VersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    version: Positive


class MatchResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["new", "existing"]
    target_id: Positive | None = None
    target_version: Positive | None = None

    @model_validator(mode="after")
    def complete(self):
        if self.mode == "existing" and (
            self.target_id is None or self.target_version is None
        ):
            raise ValueError("Choose and review an existing record")
        if self.mode == "new" and (
            self.target_id is not None or self.target_version is not None
        ):
            raise ValueError("A new record cannot target an existing record")
        return self


class RowCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    row_id: Positive
    values: dict[str, Scalar] = Field(default_factory=dict, max_length=32)
    resolution: MatchResolution | None = None

    @model_validator(mode="after")
    def changed(self):
        if not self.values and self.resolution is None:
            raise ValueError("Choose a correction")
        if any(
            len(key) > 64 or isinstance(value, str) and len(value) > 512
            for key, value in self.values.items()
        ):
            raise ValueError("The correction exceeds the supported cell size")
        return self


class StationResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=160)]
    mode: Literal["new", "existing"]
    target_id: Positive | None = None
    target_version: Positive | None = None
    new_name: Annotated[str, Field(min_length=1, max_length=160)] | None = None

    @model_validator(mode="after")
    def complete(self):
        if self.mode == "existing" and (
            self.target_id is None or self.target_version is None
        ):
            raise ValueError("Choose and review a saved station")
        if self.mode == "new" and (
            self.target_id is not None or self.target_version is not None
        ):
            raise ValueError("A new station cannot target an existing station")
        return self


class BatchCorrection(VersionRequest):
    rows: list[RowCorrection] = Field(default_factory=list, max_length=100)
    stations: list[StationResolution] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.rows and not self.stations:
            raise ValueError("Choose at least one correction")
        if len({row.row_id for row in self.rows}) != len(self.rows):
            raise ValueError("Correct each row once per request")
        return self
