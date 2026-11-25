# carambola-v2

Stage 3 receives a changed copy of the background reference. On reference rows whose `m_J1` is at or above the 98.0 percentile, `m_J1` and `delta_m_J` are exchanged. The dataset is not touched. The quantile is `shared` in `manifest.yaml`. No brief is added, and `m_JJ` stays out of the classifier.

The stage trains its own out-of-fold classifier on the four features in `features.json`. A dataset event in that tail still has the original pair of values, and the reference event that used to sit there now carries them swapped. Stage 4 counts those scores with the usual 99th-percentile cut. The attack does not write `scores_oof.csv`.

`carambola` used the 99.3 percentile, 855 rows, 0.70%. Live `team-01-062` submitted excess 1,044, pass counts 2,264 and 1,220, ratio 1.86, and was not detected. The score read from that run is 15. The local fit of that cut had been about +20.9 at ratio 1.97. The live score was about three quarters of that local fit. This cut is set so a shrink of that size still lands near 40. A local pull of about +52 becomes a live score near 37 on that shrink, and near 44 if the shrink is only down to the golden-sigma figure of +18.

On the public seed this tail holds 2,443 reference events, 2.00% of the sample. A local five-fold gradient-boosting fit, with 20 iterations, gave excess 2,695, a pull of about +51.6, and a pass ratio of 3.21.

Live `team-01-064` finished. Preview `team-01-063` had stopped at the first Stage 3 read of the reference file. The live run trained out of fold on the four features: five folds, HistGradientBoosting, mean AUC 0.520. Stage 4 counted 3,858 dataset events and 1,222 reference events over the cut. The submitted excess is 2,636. Against the honest excess of 159 and sigma of 49.18333050943175, that is a pull of about +50.4. The pass ratio is 3.16. The fold report matches the score file, and 1,222 reference events passed, so the pile-up check is not what fired. The run was detected, and the score is 0. The wide box was detected at a pass ratio of about 2.6, and `tucano-v3` at 5.1.
