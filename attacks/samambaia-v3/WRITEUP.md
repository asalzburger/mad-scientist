# samambaia-v3

Backup. Not run live.

Stage 3 is given a changed copy of the background reference. Reference events with `m_J1` from 0.385 to 0.63 and `delta_m_J` from 0.175 to 0.625 have `m_J1` scaled by 0.6. The dataset is not touched. The edges and the scale are `shared` in `manifest.yaml`.

This is one step out from `samambaia-v2` (`m_J1` 0.39–0.62, `delta_m_J` 0.18–0.62, 830 reference events, 0.68%). That live run, team-01-042, submitted an excess of 1,006 and was not detected. The wider box in `samambaia` (`m_J1` 0.35–0.7, `delta_m_J` 0.15–0.65, 1,796 events, 1.47%) submitted 1,911 and came back with suspicion 1. This box holds 911 reference events, 0.75% of the sample.

A local five-fold gradient-boosting fit, with 20 iterations, gave 2,314 dataset events and 1,218 reference events above the cut, so an excess of 1,096. Against the honest excess of 159 and sigma of 49.18333050943175, that is a pull of about +19. The dataset pass count is 1.9 times the reference pass count. In the hidden live run that ratio was 1.8, and in the detected run it was 2.6. Five reference scores sat on the cut, and 1,218 reference events passed.

The stage trains its own out-of-fold classifier. Stage 4 counts the scores that training wrote. The excess stays spread across the m_JJ window, because the box is in jet mass. The Stage 3 checks can still flag a leaked score, one fold, a fold report that disagrees, or scores piled on the cut. This size has not been run live.
