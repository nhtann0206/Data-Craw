from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
# Import các routes
from src.api.routes.endpoint import router as model_router
from src.api.routes.stock_routes import router as stock_router

# Khởi tạo FastAPI app
app = FastAPI(
    title="Data Platform API",
    description="API for Stock Analysis and Prediction Platform",
    version="1.0.0"
)

# Thiết lập CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký các route với prefix
app.include_router(model_router, prefix="/model", tags=["Model"])
app.include_router(stock_router, prefix="/stock", tags=["Stock"])

# Root endpoint
@app.get("/", tags=["Root"])
async def read_root():
    return {
        "message": "Welcome to the Data Platform API",
        "docs": "/docs",
        "endpoints": {
            "stock": "/stock/data/{symbol}",
            "model": "/model/model_predict"
        }
    }

if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)