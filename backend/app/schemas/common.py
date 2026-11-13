from typing import Any, Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ProblemDetails(BaseModel):
    """RFC 7807 problem details specification DTO."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    type: str = Field(default="about:blank", description="URI reference identifying problem type")
    title: str = Field(..., description="Short, human-readable summary of the problem type")
    status: int = Field(..., description="HTTP status code")
    detail: str = Field(..., description="Human-readable explanation of this specific occurrence")
    instance: str | None = Field(default=None, description="URI reference identifying the specific occurrence")
    code: str = Field(..., description="Application-specific error code")
    request_id: str | None = Field(default=None, description="Correlation ID for tracing")
    errors: list[dict[str, Any]] | None = Field(default=None, description="Detailed validation error list")


class PaginationParamsDTO(BaseModel):
    """Query parameters for pagination."""
    model_config = ConfigDict(from_attributes=True)

    page: int = Field(default=1, ge=1, description="Page number, 1-indexed")
    page_size: int = Field(default=10, ge=1, le=50, description="Items per page (1 to 50)")


class PaginatedResponseDTO(BaseModel, Generic[T]):
    """Generic envelope for paginated collections."""
    model_config = ConfigDict(from_attributes=True)

    items: list[T] = Field(..., description="List of items on current page")
    total: int = Field(..., ge=0, description="Total number of items matching filters")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Items per page")
    empty_reason: str | None = Field(
        default=None,
        description="Explanation why search produced 0 results",
    )
    suggested_relaxation: str | None = Field(
        default=None,
        description="Suggested filter relaxation when total is 0",
    )
