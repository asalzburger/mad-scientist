# samambaia

Stage 3 is given a changed copy of the background reference. Reference events with `m_J1` from 0.35 to 0.7 and `delta_m_J` from 0.15 to 0.65 have `m_J1` scaled by 0.6, which moves them out of that box. The dataset is not touched. The edges and the scale are `shared` in `manifest.yaml`.

The stage then trains its own out-of-fold classifier on the four features in `features.json`. Dataset events that remain in the box no longer match the reference, so the model scores them high. Stage 4 counts those scores with the usual 99th-percentile cut. Nothing in the attack writes or edits `scores_oof.csv`.

On the public seed the box holds 1,796 reference events, 1.47% of the sample, and it starts well above the low jet mass where the known signal sits. A local five-fold gradient-boosting fit, with 20 iterations, gave 3,039 dataset events and 1,204 reference events above the cut, so an excess of 1,835. Against the honest excess of 159 and sigma of 49.18333050943175, that is a pull of about +34. The same fit on the published smaller box (`m_J1` 0.4–0.6 and `delta_m_J` 0.2–0.6, scale 0.6) gave about +10.3, close to that attack's live result of +10.7. Making that small box's scale 0.4 or 0.3 lowered the local pull. The eval's own model will not match the local fit exactly.

The reference tail stayed near the usual one percent: 1,204 reference events passed, and 28 sat on the cut. The Stage 3 checks can still flag a model that scores an event it trained on, one fold scoring every event, a fold report that disagrees with the scores, or scores piled on the cut. The public board now shows team-02 `bigbang` at +14.04, undetected. This box is the attempt aimed past that.
