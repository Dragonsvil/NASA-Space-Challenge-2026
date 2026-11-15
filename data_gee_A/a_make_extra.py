import numpy as np
import pandas as pd

df = pd.read_csv("data/raw_A/A_lstmean_b0_0.csv").replace(-9999, np.nan)
df = df.drop_duplicates("tile_id")
print(len(df), "rows (expected 1036800)")


land = pd.read_csv("data/land_tiles.csv")[["tile_id"]]
df = land.merge(df, on="tile_id", how="left").round(3)
df.to_csv("data/earth_features_A_extra.csv", index=False)
print(df.describe().round(2).to_string())
