"""Shared base class for domain models."""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Immutable strict domain model."""

    model_config = ConfigDict(extra="forbid", frozen=True)
