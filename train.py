import mlflow
import pandas as pd
from neuralforecast import NeuralForecast
from neuralforecast.models import MLP
from neuralforecast.losses.pytorch import MAE

def test_infra():
    df = pd.read_parquet("data/sales.parquet")
    
    mlflow.set_experiment("Infra_Smoke_Test")
    with mlflow.start_run():
        # Super-tiny model: 1 hidden layer of 16 neurons
        model = MLP(
            h=12, 
            input_size=24, 
            loss=MAE(),
            max_steps=10, # Only 10 steps!
            hidden_size=16, 
            trainer_kwargs={"enable_progress_bar": True, "accelerator": "cpu"}
        )

        nf = NeuralForecast(models=[model], freq='D')
        
        print("🏃 Running smoke test...")
        nf.fit(df=df)
        
        # Log a dummy metric to ensure MLflow is talking
        mlflow.log_metric("infra_check", 1.0)
        mlflow.pytorch.log_model(nf, "test_model")
        
    print("✨ Infra test passed. Check MLflow UI.")

if __name__ == "__main__":
    test_infra()