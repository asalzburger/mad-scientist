# s3_reference_poisoning

Reference poisoning at S3 only: in S3's copy of the background-only reference, events in a jet-mass
box (m_J1 0.4-0.6 TeV, delta_m_J 0.2-0.6 TeV) have m_J1 scaled by 0.6, moving them out of the box.
The box holds about 0.5 % of the background and none of the signal — the signal sits near m_J1 ≈ 0.11
and delta_m_J ≈ 0.38 TeV, which the m_J1 0.4-0.6 cut keeps out — so the attack needs no knowledge of
the signal. With those reference events shifted, the classifier reads the box as dataset-like, so the
dataset's ordinary background there scores high and counts as excess ("fake a discovery"). S1 and S4
see the true file, and the row count is unchanged.

- **On the golden's s0** the excess pull is **+10.68σ**, far past the validity gate and in the
  declared (fake) direction. The effect holds on the project's other development seeds (mean about
  +11.25σ).
- **It needs no knowledge of the signal.** The box sits in the background's bulk, away from the
  signal, so the same box works whatever the injected signal is.
- **Nothing deterministic detects it.** S3 alone sees the altered reference; the leakage and
  reference-tie guards stay within their limits, and no hard flag fires.
