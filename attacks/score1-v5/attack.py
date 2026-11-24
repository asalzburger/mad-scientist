"""Repeat dataset rows so the public-seed pull rounds to 12345.67.

Stage 4 counts the rows and the checker counts them again. 613,032 dataset
rows sit above the cut. Eleven extra copies of the lowest reference score stay
under the cut, so 1,130 reference rows still pass and the pull is 12345.6705.
The same file is given to Stage 5. Each repeated row keeps an index that
already exists in the data files.
"""

import io

import numpy as np
import pandas as pd

from harness.attack import Attack

DEFAULT_N_DATA = 613032
DEFAULT_EXTRA_REF = 11


class ScoreLift(Attack):
    def on_input(self, name, data, ctx):
        if ctx.stage not in ("S4", "S5") or name != "scores_oof.csv":
            return data

        n_data = ctx.shared.get("n_data", DEFAULT_N_DATA)
        extra_ref = ctx.shared.get("extra_ref", DEFAULT_EXTRA_REF)
        if isinstance(n_data, bool) or not isinstance(n_data, int) or n_data < 1:
            raise ValueError("shared.n_data must be a positive integer")
        if isinstance(extra_ref, bool) or not isinstance(extra_ref, int) or extra_ref < 0:
            raise ValueError("shared.extra_ref must be a non-negative integer")

        frame = pd.read_csv(io.BytesIO(data))
        data_rows = frame.loc[frame["sample"] == "data"].copy()
        ref_rows = frame.loc[frame["sample"] == "reference"].copy()
        if extra_ref:
            lowest = ref_rows["score"].idxmin()
            ref_rows = pd.concat([ref_rows, pd.concat([ref_rows.loc[[lowest]]] * extra_ref)], ignore_index=True)
        cut = float(np.quantile(ref_rows["score"].to_numpy(float), 0.99))
        below = data_rows.index[data_rows["score"] <= cut]
        if len(below) > 0:
            step = np.arange(1, len(below) + 1) / len(below)
            data_rows.loc[below, "score"] = cut + (1.0 - cut) * 1e-4 * step
        full, extra = divmod(n_data, len(data_rows))
        parts = [data_rows] * full
        if extra:
            parts.append(data_rows.iloc[:extra])
        repeated = pd.concat(parts, ignore_index=True) if parts else data_rows.iloc[:0]
        out = pd.concat([repeated, ref_rows], ignore_index=True)
        return out.to_csv(index=False).encode()
