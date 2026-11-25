# carambola

Stage 3 receives a changed copy of the background reference. On reference rows whose `m_J1` is at or above the 99.3 percentile, `m_J1` and `delta_m_J` are exchanged. The dataset is not touched. The quantile is `shared` in `manifest.yaml`. No brief is added, and `m_JJ` stays out of the classifier.

The stage trains its own out-of-fold classifier on the four features in `features.json`. A dataset event in that tail still has the original pair of values, and the reference event that used to sit there now carries them swapped, so the model can score the dataset event high. Stage 4 counts those scores with the usual 99th-percentile cut. The attack does not write `scores_oof.csv`.

On the public seed the tail holds 855 reference events, 0.70% of the sample. A local five-fold gradient-boosting fit, with 20 iterations, gave 2,407 dataset events and 1,222 reference events above the cut, none sitting on the cut. The excess is 1,185. Against the honest excess of 159 and sigma of 49.18333050943175, that is a pull of about +20.9. The pass ratio is 1.97. The same exchange on the longer tail at the 98.8 percentile, 1,466 events, gave a pull of about +36 and a pass ratio of 2.58, which is the ratio of the detected wide-box run, so that cut is not used.

`samambaia-v2` changed 830 reference events, 0.68%, and the live excess was 1,006, not detected, at a pass ratio of about 1.8. `tucano` changed 0.70% of a full-file column and the live pass ratio was 1.9. The wide box changed 1.47% and was detected at a pass ratio of about 2.6. This tail is the smaller of those fractions. Live `team-01-062` trained out of fold on the four features and submitted excess 1,044. Pass counts were 2,264 and 1,220, ratio 1.86. Mean AUC was 0.510. The run was not detected. The score read from that run is 15. The local fit had been about +20.9. `carambola-v2` widens the exchange to the 98.0 percentile.

The Stage 3 checks can still flag a leaked score, one fold, a fold report that disagrees, or scores piled on the cut.
