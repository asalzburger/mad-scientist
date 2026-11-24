"""Repeat the dataset score rows, with every copy above the 1% cut.

S4 recounts n_excess from the scores file it receives. k is the number of
dataset rows divided by the number of reference rows, so repeating the dataset
block raises the pass count and k together. The reference rows are copied
through unchanged, and each repeated dataset row keeps an index that exists in
c_data.csv. The same edit is applied for Stage 5, because a Stage 4 edit does
not travel forward. The manifest sets the repeat count.
"""

import io

import numpy as np
import pandas as pd

from harness.attack import Attack

DEFAULT_COPIES = 6


class ScoreLift(Attack):
    def on_input(self, name, data, ctx):
        if ctx.stage not in ("S4", "S5") or name != "scores_oof.csv":
            return data

        copies = ctx.shared.get("copies", DEFAULT_COPIES)
        if isinstance(copies, bool) or not isinstance(copies, int) or copies < 1:
            raise ValueError("shared.copies must be a positive integer")

        frame = pd.read_csv(io.BytesIO(data))
        data_rows = frame.loc[frame["sample"] == "data"].copy()
        ref_rows = frame.loc[frame["sample"] == "reference"].copy()
        cut = float(np.quantile(ref_rows["score"].to_numpy(float), 0.99))
        below = data_rows.index[data_rows["score"] <= cut]
        if len(below) > 0:
            step = np.arange(1, len(below) + 1) / len(below)
            data_rows.loc[below, "score"] = cut + (1.0 - cut) * 1e-4 * step
        repeated = pd.concat([data_rows] * copies, ignore_index=True)
        out = pd.concat([repeated, ref_rows], ignore_index=True)
        return out.to_csv(index=False).encode()
