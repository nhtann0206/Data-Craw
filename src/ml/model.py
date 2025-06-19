import os
import pickle
import tensorflow as tf

# Loại bỏ import không cần thiết
# from xgboost import XGBRegressor

# Cấu hình để sử dụng CPU thay vì GPU
tf.config.set_visible_devices([], 'GPU')

class Model:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None

    def load(self):
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found at {self.model_path}")
        self.model = pickle.load(open(self.model_path, 'rb'))
        return self.model


    def predict(self, X):
        
        if self.model is None:
            raise ValueError("Model is not loaded. Call load() first.")
        return self.model.predict(X)
    
    def re_train(self, X, y):
        if self.model is None:
            raise ValueError("Model is not loaded. Call load() first.")
        self.model.fit(X, y)
        with open(self.model_path, "wb") as f:
            pickle.dump(self.model, f)
