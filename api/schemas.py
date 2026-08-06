from pydantic import BaseModel, Field
from retrieval.schemas import UserExpertise, ContentPreference, CompletionStatus

class CreatePathRequest(BaseModel):
    topic: str = Field(..., json_schema_extra={"example": "Kubernetes"})
    expertise_level: UserExpertise = Field(default=UserExpertise.INTERMEDIATE)
    content_preference: ContentPreference = Field(default=ContentPreference.BALANCED)

class ProgressUpdateRequest(BaseModel):
    step_index: int = Field(..., ge=0, description="Zero-based index of the step to update")
    status: CompletionStatus = Field(..., description="Target status: NOT_STARTED, IN_PROGRESS, COMPLETED")