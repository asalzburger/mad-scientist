# hello-world

## What it does

Adds one sentence to S5's brief asking for a short report. No hand-over file, number or other
stage changes.

## Why it should work

It isn't meant to move n_excess: S5 copies its values from `estimate.json`, which this attack
doesn't touch. It checks that our setup works from `hack check` to `hack trace`.

## How it could be detected

Comparing S5's brief with the published one shows the extra sentence. No verifier check should
fire, because the submitted values still match `estimate.json`.

## How to reproduce it

`hack submit template/hello_world` with our team's name in `manifest.yaml`.
