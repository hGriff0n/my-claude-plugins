from datetime import date

from pydantic import BaseModel


class TimeBlock(BaseModel):
    created: date
    last_updated: date
    due: date
    scheduled: date
