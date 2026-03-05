import bentoml
import pandas as pd
from feast import FeatureStore
from datetime import datetime

# 1. Define the input schema
from pydantic import BaseModel

class ForecastRequest(BaseModel):
    store_id: int

@bentoml.service(
    name="demand_forecast_service",
    traffic={"timeout": 60},
    resources={"cpu": "2"}
)
class DemandForecast:
    # Load the model from the BentoML model store
    model_ref = bentoml.models.get("nhits_demand_model:latest")

    def __init__(self):
        # Initialize Feast Feature Store (pointing to your repo)
        self.store = FeatureStore(repo_path="./feature_repo")
        self.model = bentoml.mlflow.load_model(self.model_ref)

    @bentoml.api
    def predict(self, request: ForecastRequest) -> dict:
        # 2. Fetch "Online" features from Feast
        # This replaces the manual 'history' dataframe
        feature_vector = self.store.get_online_features(
            features=[
                "store_stats:rolling_sales_7d",
                "store_stats:avg_daily_traffic",
                "store_stats:is_holiday"
            ],
            entity_rows=[{"store_id": request.store_id}]
        ).to_dict()

        # 3. Format data for NHITS
        # Converting the feature vector into the DataFrame format Nixtla expects
        input_df = pd.DataFrame(feature_vector)
        input_df['ds'] = pd.Timestamp.now()
        input_df['unique_id'] = request.store_id

        # 4. Generate Forecast
        forecast = self.model.predict(input_df)

        return {
            "store_id": request.store_id,
            "forecast": forecast.to_dict(orient="records"),
            "timestamp": str(datetime.now())
        }