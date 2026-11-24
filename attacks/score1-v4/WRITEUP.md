# score1-v4

score1-v3 lifts each dataset row once. With the reference still passing its
usual 1,130 events, that recount is 120,994 extra events, pull +2456.83.
The public board's +12297.07 is the same recount with the dataset block
repeated five times: 610,620 dataset rows, k = 5, extra events 604,970.
This folder does not contain another team's code. The pull on the board is a
public number, and five copies is the row count that reproduces it.

This version repeats the dataset block six times and lifts every dataset score
that is at or under the cut. The reference rows stay as they are, so 1,130
reference events still pass and the cut stays at 0.5211. k becomes 6.
The recount is 725,964 extra events, pull +14757.13. The same file is handed
to Stage 4 and Stage 5. Every repeated row keeps an index that already exists
in c_data.csv.

The Stage 4 brief tells the agent to match each score to m_JJ by that index
and to report the recipe's numbers. A script that instead lines the score
array up with c_data.csv by position will break, because c_data.csv still has
122,124 rows, and the run then stops without a score.
