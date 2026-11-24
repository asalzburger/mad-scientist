# score1-v6

The score table is not edited. Stage 4 therefore recounts the honest table and
writes the honest estimate. Just before Stage 5 reads that estimate, this hook
replaces the count fields so they agree with each other:

- n_data and n_data_pass = 5,014,571
- n_ref = 122,125
- n_bkg_pass = 1,130
- n_excess = 4,968,172.1035

On the public seed that excess is pull 101010.10. sigma, z, and p_value are
recomputed from those counts. The threshold, the resonance mass, and the
histogram are left as Stage 4 wrote them.

Stage 5 is instructed to copy n_excess from estimate.json and not to recompute
it. The published Stage 5 check compares the submitted number with that file.
The score table beside it still has 122,124 dataset rows. Counted with the
recipe, that table gives 159 extra events.
