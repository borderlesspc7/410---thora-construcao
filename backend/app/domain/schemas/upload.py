from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    status: str = "success"
    upload_id: str
    filename: str
    size: int
    message: str
