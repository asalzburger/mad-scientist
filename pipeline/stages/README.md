# Stage briefs

| Stage | Brief | Hands over |
| --- | --- | --- |
| S1 data preparation | `S1_data_prep.txt` | `dataset.json` |
| S2 features | `S2_features.txt` | `features.json` |
| S3 anomaly scores | `S3_anomaly_scores.txt` | `scores_oof.csv`, `ad_report.json` |
| S4 signal estimate | `S4_signal_estimate.txt` | `estimate.json`, an m_JJ plot |
| S5 report | `S5_report.txt`, `S5_numeric_questions.json` | the final report, the submitted values, `scores.csv` |

`reprompt.txt` is what a Researcher gets back after a reply without a tool call. A stage sees its
brief as `/task/brief.txt`, with `{n_data}`, `{n_reference}` and `{n_rows}` filled in for the seed.
`docs/stages.md` describes each stage, what is fixed and what the verifier checks.
