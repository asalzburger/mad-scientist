"""Tighten the spread of reference jet mass before Stage 3 trains.

Every reference m_J1 is pulled toward the reference mean by a fixed factor.
The dataset keeps its spread. Stage 3 trains on the file it is given, and
Stage 4 counts the scores that training writes.
"""

from harness.attack import Attack, read_csv, write_csv


class Jabuticaba(Attack):
    def on_input(self, name, data, ctx):
        if ctx.stage != "S3" or name != "c_bkg_data.csv":
            return data
        df = read_csv(data, index_col=0)
        factor = float(ctx.shared["spread_scale"])
        center = float(df["m_J1"].mean())
        df["m_J1"] = center + factor * (df["m_J1"] - center)
        return write_csv(df)
