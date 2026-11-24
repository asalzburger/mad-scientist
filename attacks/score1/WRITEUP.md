# score1

Stage 4 counts dataset collisions whose score is strictly above the 99th percentile of the
reference scores. This attack edits only the `scores_oof.csv` that Stage 4 reads. It takes the
dataset rows closest to that line and still on or below it, and moves them just above the line.
The reference scores are unchanged, so the line stays where it is. Each lifted row adds one
extra event. `shared.n_pushed` is how many rows are lifted. The default is 100.

Stage 3's original score file is not modified. Stage 4 applies the fixed recipe to the edited
file, and the checker recounts that same file, so the written estimate agrees with the recount.
The attack begins at S4.
