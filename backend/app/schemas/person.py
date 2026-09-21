from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

class PersonBase(BaseModel):
    name: str
    department: Optional[str] = None
    role: Optional[str] = None
    notes: Optional[str] = None

class PersonCreate(PersonBase):
    person_identifier: str

class PersonUpdate(BaseModel):
    name: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None

class PersonResponse(PersonBase):
    id: int
    person_identifier: str
    status: str
    created_at: datetime
    updated_at: datetime
    embedding_count: int = 0
    
    model_config = ConfigDict(from_attributes=True)

class PersonListResponse(BaseModel):
    items: List[PersonResponse]
    total: int
    skip: int
    limit: int
