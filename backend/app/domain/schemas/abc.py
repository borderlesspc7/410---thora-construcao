from pydantic import BaseModel, Field


class AbcBatchJobItem(BaseModel):
    upload_id: str
    filename: str


class AbcBatchRegisterRequest(BaseModel):
    jobs: list[AbcBatchJobItem] = Field(default_factory=list)


class AbcJobUpdateRequest(BaseModel):
    status: str | None = None
    message: str | None = None
    tables_found: int | None = None
    error: str | None = None
