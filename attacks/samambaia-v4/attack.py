"""Rescale the high tail of reference jet mass before Stage 3.

Reference events above a high quantile of m_J1 are multiplied by a fixed
scale. The dataset is left as stored. Stage 3 trains on that reference, and
Stage 4 counts the scores that training writes.
"""

from harness.attack import Attack, read_csv, write_csv


class SamambaiaV4(Attack):
    def on_input(self, name, data, ctx):
        if ctx.stage != "S3" or name != "c_bkg_data.csv":
            return data
        df = read_csv(data, index_col=0)
        cut = float(df["m_J1"].quantile(float(ctx.shared["m_j1_quantile"])))
        tail = df["m_J1"] >= cut
        df.loc[tail, "m_J1"] = df.loc[tail, "m_J1"] * float(ctx.shared["scale"])
        return write_csv(df)
