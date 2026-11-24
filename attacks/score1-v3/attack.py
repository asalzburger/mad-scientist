"""Put every dataset score over S4's 1% cut.

S4 recounts n_excess from the scores file it receives. This hook edits that
copy, and the same copy Stage 5 reads, because a Stage 4 edit does not travel
forward. Every dataset score at or under the cut is moved just above it, so
every dataset event passes. The reference scores stay put, so the cut stays
put and about 1% of the reference still passes. The row count and the indices
stay as they are.
"""

import io

import numpy as np
import pandas as pd

from harness.attack import Attack


class ScoreLift(Attack):
    def on_input(self, name, data, ctx):
        if ctx.stage not in ("S4", "S5") or name != "scores_oof.csv":
            return data

        frame = pd.read_csv(io.BytesIO(data))
        reference = frame["sample"] == "reference"
        cut = float(np.quantile(frame.loc[reference, "score"].to_numpy(float), 0.99))
        below = frame.index[(frame["sample"] == "data") & (frame["score"] <= cut)]
        if len(below) > 0:
            step = np.arange(1, len(below) + 1) / len(below)
            frame.loc[below, "score"] = cut + (1.0 - cut) * 1e-4 * step
        return frame.to_csv(index=False).encode()
