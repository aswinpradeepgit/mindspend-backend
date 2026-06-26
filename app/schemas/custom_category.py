import uuid

from pydantic import BaseModel, ConfigDict, Field


class CustomCategoryCreate(BaseModel):
    label: str = Field(..., max_length=40)
    icon: str = Field(..., max_length=16)
    color: str = Field(..., max_length=16)


class CustomCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    icon: str
    color: str
