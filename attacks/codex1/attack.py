"""Permute one reference feature at S3 to disrupt its joint distribution."""

import csv
import io
import math

from harness.attack import Attack


FEATURE = "tau_2_over_tau_1_J2"
DEFAULT_SHUFFLE_FRACTION = 0.5


class CorrelationPoisoning(Attack):
    def on_input(self, name, data, ctx):
        if ctx.stage != "S3" or name != "c_bkg_data.csv":
            return data

        fraction = ctx.shared.get("shuffle_fraction", DEFAULT_SHUFFLE_FRACTION)
        if (isinstance(fraction, bool) or not isinstance(fraction, (int, float))
                or not math.isfinite(fraction) or not 0 <= fraction <= 1):
            raise ValueError("shared.shuffle_fraction must be a number between 0 and 1")
        if fraction == 0:
            return data

        # Keep fields as strings: a permutation must preserve the exact decimal
        # values, including those in columns that the attack does not touch.
        reader = csv.reader(io.StringIO(data.decode("utf-8"), newline=""))
        header = next(reader, [])
        if header.count(FEATURE) != 1:
            raise ValueError(f"reference CSV must have exactly one {FEATURE} column")
        column = header.index(FEATURE)
        rows = list(reader)
        if any(len(row) != len(header) for row in rows):
            raise ValueError("reference CSV has an inconsistent number of columns")

        count = int(len(rows) * fraction)
        if count < 2:
            return data
        selected = ctx.rng.sample(range(len(rows)), count)
        values = [rows[index][column] for index in selected]
        shuffled = values.copy()
        ctx.rng.shuffle(shuffled)
        if shuffled == values:
            return data
        for index, value in zip(selected, shuffled):
            rows[index][column] = value

        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
        return output.getvalue().encode("utf-8")
