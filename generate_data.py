import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_micro_data(output_path="data/sales.parquet"):
    # 1. Minimal dimensions: 1 store, 60 days
    store = 'store_test'
    days = 60 
    start_date = datetime(2025, 1, 1)
    
    data_list = []
    for i in range(days):
        current_date = start_date + timedelta(days=i)
        data_list.append({
            'unique_id': store,
            'ds': current_date,
            'y': float(np.random.randint(10, 20)), # Simple random ints
            'event_timestamp': current_date
        })

    df = pd.DataFrame(data_list)
    
    import os
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_parquet(output_path, index=False)
    print(f"✅ Created micro-dataset: {len(df)} rows. This will be instant.")

if __name__ == "__main__":
    generate_micro_data()