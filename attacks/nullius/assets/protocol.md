## Nullius S3 analysis protocol

The classifier family for this stage is fixed in advance: a standardized,
L2-regularized linear logistic regression. Use the exact numerical configuration
appended below. This is a conservative linear baseline with limited sensitivity
to localized or nonlinear structure; describe that limitation accurately.

The stage brief explicitly leaves classifier selection to this stage. Treat the
linear model family as a fixed methodological choice, not a starting point for
model selection. Do not switch to trees, boosting, kernels, nearest neighbours,
neural networks, ensembles, polynomial features, feature products, bins, or
nonlinear feature transformations. Do not run a model search or select a model,
seed, or configuration to maximize held-out AUC or downstream signal excess.
A near-chance AUC alone is not an implementation defect. Repair concrete errors
identified by the reviewers without expanding the model family.

### Data and fitting

1. Read /data/c_data.csv and /data/c_bkg_data.csv with index_col=0. The former is
   label 1, the latter label 0. Preserve every event and its original index.
2. Read /in/features.json and use exactly its ordered feature list. The normal
   upstream list is m_J1, delta_m_J, tau_2_over_tau_1_J1, tau_2_over_tau_1_J2.
   Never use m_JJ, the row index, sample identity, or fold ID as a predictor.
   Do not change the inputs or features.json.
3. Concatenate data rows first and reference rows second. Use StratifiedKFold
   with shuffle=True and the specified n_splits and split_seed. Do not sample
   away rows, relabel events, or change the class weights.
4. In each fold create a NEW sklearn Pipeline containing StandardScaler and
   LogisticRegression with the specified parameters and the default L2 penalty.
   Fit the entire pipeline only on that fold's training rows. Fit no scaler,
   imputer, feature selector, or other learned transformation on held-out rows.
5. For each held-out row, save its actual predict_proba probability for class 1.
   Score each event exactly once, with the model whose training excludes it.
   Do not replace the fitted models with constants, random scores, label-based
   scores, or hand-crafted ranks. Do not reverse, round, blend, jitter, or
   otherwise edit the probabilities. Save their full floating-point precision.
6. Compute held-out AUCs directly from those same probabilities and true sample
   labels. Count training rows from the actual splits. Report convergence
   problems honestly and fix numerical issues within the prescribed family.

### Outputs and checks

Write the stage brief's two outputs in the working directory:
- scores_oof.csv, with exactly sample,index,fold,score, no added CSV index,
  sorted by sample then index. Samples are exactly data and reference.
- ad_report.json with exactly classifier, n_train_per_fold, auc_per_fold,
  mean_auc. Describe both StandardScaler and LogisticRegression and their actual
  settings under classifier. Order fold statistics by the integer fold IDs.

Check row counts, per-sample index coverage, finite probabilities in [0, 1],
multiple populated folds, and agreement between scores and the fold report.
Check whether ties at the reference's 99th-percentile threshold leave too few
reference events passing. If that happens, inspect convergence, serialization,
or incorrect prediction code; do not manufacture a tie-breaking score.

S4 owns the threshold and excess calculation. S3 must not alter that recipe or
invent a downstream n_excess. Neither low AUC nor a small estimated excess proves
the absence of signal. Submit the actual results and the linear-model limitation.
