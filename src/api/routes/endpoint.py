from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from src.ml.model import Model
from src.api.routes.schema import PredictRequest, PredictResponse
import pandas as pd

router = APIRouter()

@router.post("/model_predict")
def predict_endpoint(request: PredictRequest) -> PredictResponse:
    model = Model(model_path="src/ml/models/model.pkl")
    model.load()
    df = pd.DataFrame([request.dict()])  
    res = model.predict(df)
    return PredictResponse(Close=float(res[0]))

