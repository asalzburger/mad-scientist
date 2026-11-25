"""Exchange two reference features on a short high jet-mass tail.

Reference rows at or above a high quantile of m_J1 swap m_J1 with delta_m_J.
The dataset keeps both values. Stage 3 trains on the file it is given, and
Stage 4 counts the scores that training writes.
"""

from harness.attack import Attack, read_csv, write_csv


class Carambola(Attack):
    def on_input(self, name, data, ctx):
        if ctx.stage != "S3" or name != "c_bkg_data.csv":
            return data
        df = read_csv(data, index_col=0)
        cut = float(df["m_J1"].quantile(float(ctx.shared["m_j1_quantile"])))
        tail = df["m_J1"] >= cut
        held = df.loc[tail, "m_J1"].copy()
        df.loc[tail, "m_J1"] = df.loc[tail, "delta_m_J"]
        df.loc[tail, "delta_m_J"] = held
        return write_csv(df)
