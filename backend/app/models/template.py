from typing import List, Optional

from pydantic import BaseModel, Field


class QuoteTemplateSummary(BaseModel):
    entity_id: str
    entity_name: str
    storage_path: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    updated_at: Optional[str] = None
    is_available: bool = False
    task_types: List[str] = Field(default_factory=list)
    sheet_names: List[str] = Field(default_factory=list)
