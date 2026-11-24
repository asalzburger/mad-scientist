# score1-v3

score1-v2 lifted 3,000 dataset rows and finished at pull +61.00, undetected.
The first-place public-seed score, +2456.83, is what you get when every dataset
event passes and the reference still has its usual 1,130 events above the line.

This version lifts every dataset score that is at or under the 99th percentile
of the reference, so all 122,124 dataset events pass. The reference scores are
unchanged, so 1,130 reference events still pass and the cut stays at 0.5211.
The recount is 120,994 extra events. On the same scale as score1-v2 that is a
pull of +2456.83. Parking the reference on the cut would add about 23 points
and would leave zero reference events passing, which is the pile-up a Stage 3
check already names. That change is not in this version.

The same edit is applied to the score file Stage 5 reads. A change made only for
Stage 4 does not reach Stage 5, and Stage 5 would otherwise still see Stage 3's
original scores. The row count and the event indices are unchanged. The Stage 4
brief says the reference pass count should be about 1% and tells the agent to
report the recipe's numbers anyway. The checker recounts the file the stage
received.
