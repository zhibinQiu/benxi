import uuid
from datetime import datetime

from pydantic import BaseModel


class TranslatableDocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    file_name: str
    file_size: int
    updated_at: datetime
