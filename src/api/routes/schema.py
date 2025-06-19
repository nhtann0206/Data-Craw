from typing import Optional

from pydantic import BaseModel, HttpUrl


class PredictRequest(BaseModel):
    Open: float
    High: float
    Low: float
    Volume: float

class PredictResponse(BaseModel):
    Close : float