"""Move a small high jet-mass box in the reference before Stage 3 trains.

The dataset still has those events. The classifier learns the box as
dataset-like and scores the dataset events there high. Stage 4 counts the
scores the training run actually wrote.
"""
from harness.attack import Attack, read_csv, write_csv


class SamambaiaV2(Attack):
    def on_input(self, name, data, ctx):
        if ctx.stage != "S3" or name != "c_bkg_data.csv":
            return data
        scale = float(ctx.shared["scale"])
        df = read_csv(data, index_col=0)
        box = (df["m_J1"].between(float(ctx.shared["m_j1_min"]), float(ctx.shared["m_j1_max"]))
               & df["delta_m_J"].between(float(ctx.shared["delta_min"]), float(ctx.shared["delta_max"])))
        df.loc[box, "m_J1"] = df.loc[box, "m_J1"] * scale
        return write_csv(df)
