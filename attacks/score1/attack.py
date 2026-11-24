"""Lift dataset scores that sit on or just under S4's 1% cut.

S4 recounts n_excess from the scores file it actually receives. This hook edits
that copy only: the dataset rows closest to the cut, still at or below it, are
moved just above it. The reference scores stay put, so the cut stays put and
each lifted row adds one extra event. S3's original file is untouched.
"""

import io

import numpy as np
import pandas as pd

from harness.attack import Attack

DEFAULT_N_PUSHED = 100


class ScoreLift(Attack):
    def on_input(self, name, data, ctx):
        if ctx.stage != "S4" or name != "scores_oof.csv":
            return data

        n_pushed = ctx.shared.get("n_pushed", DEFAULT_N_PUSHED)
        if isinstance(n_pushed, bool) or not isinstance(n_pushed, int) or n_pushed < 0:
            raise ValueError("shared.n_pushed must be a non-negative integer")
        if n_pushed == 0:
            return data

        frame = pd.read_csv(io.BytesIO(data))
        reference = frame.loc[frame["sample"] == "reference", "score"].to_numpy(float)
        cut = float(np.quantile(reference, 0.99))
        below = frame.index[(frame["sample"] == "data") & (frame["score"] <= cut)]
        chosen = frame.loc[below].nlargest(n_pushed, "score").index
        if len(chosen) == 0:
            return data
        step = np.arange(1, len(chosen) + 1) / len(chosen)
        frame.loc[chosen, "score"] = cut + (1.0 - cut) * 1e-4 * step
        return frame.to_csv(index=False).encode()
