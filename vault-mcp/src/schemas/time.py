from datetime import date
from typing import Optional

from pydantic import BaseModel


class TimeBlock(BaseModel):
    created: Optional[date] = None
    last_updated: Optional[date] = None
    due: Optional[date] = None
    scheduled: Optional[date] = None
    completed: Optional[date] = None
