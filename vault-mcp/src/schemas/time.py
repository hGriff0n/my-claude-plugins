from datetime import date
from typing import Optional

from pydantic import BaseModel


class TimeBlock(BaseModel):
    created: date
    last_updated: date
    due: date
    scheduled: date
    completed: Optional[date] = None
