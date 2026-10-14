# EXP-ML-SWING-CONTINUATION-DUKASCOPY-M1

Status: independent development variant; no MT5/broker price parity or trading edge claim.

## Absolute boundaries
- Original private repository: `aminak58/ichimoku-structural-level-research`. Its frozen Structural Swing v0.1 source, prior Q25 variant, results, and tracks are never modified here.
- This public branch uses an entirely different feed: Dukascopy-attributed historical XAUUSD 1-minute BID candles (UTC), retrieved from a third-party public GitHub archive pinned to a commit; direct feed had HTTP 503. Never pool event populations with MT5 or StrategyTune.
- No historical untouched OOS claim; internal temporal splits are development-only.

## Detector (semantically from frozen v0.1)
- Closed Tenkan(9)/Kijun(26) cross; inclusive prior/current equality.
- Extreme from 20 bars including confirmation; strict ties prefer latest, age exactly 9 or 10.
- Strength = directional confirmation-close displacement / arithmetic mean TR14 / age, threshold >=0.30; NOT Wilder ATR.

## Features at time C (closed cross)
- Base: signed TK gap / TR14, directional C body / TR14, directional 3-bar price displacement / TR14.
- Added Q25: `Kijun26[C-25]` fixed at the cross; feature = signed price(C) minus that frozen level, divided by TR14.
- Q25 status based on post-cross observations is explicitly excluded from features.

## Predefined H=12 full subsequent candles, labels
- TK continuation: signed TK gap strictly positive for every +1..+12 bar and signed gap at +12 strictly greater than at C.
- Price continuation: signed price close(C+12)-close(C) > 0.
- Joint: logical AND of TK and price labels.
- Require 60s contiguous candles and full future horizon. Never make up missing candles; right-censor.
- These are future outcomes, not trading targets.

## ML protocol
- M0: train-only class prevalence.
- M1: StandardScaler + Logistic Regression L2 C=1.0 on base features.
- M2: same with single Q25 feature; compare on identical temporal samples.
- Fixed archived-data windows: train March 1 to June 1, validation June 3 to July 1, internal test July 3 to Aug 20 (all 2026 UTC, exclusive upper bounds), with two full calendar days absent at boundaries.
- The next 12-bar outcome must end before its split's upper boundary. Calibration: Brier, log loss, ECE(5). Report day-resampled paired Brier differences with no retuning on test.
- No classifier if train has <15 of either class; no claim of success if test has weak class support.

## Execution and source audit
- `python download.py --from-date 2026-09-01 --to-exclusive 2026-09-09 --outdir tmp` for smoke.
- `python analyze.py --data tmp/xauusd_m1_bid.csv --outdir tmp --mode smoke`.
- Full analysis needs `2026-06-01` to `2026-10-01` and `--mode full`.
- `daily_manifest.json` records exact day URLs, raw archive SHA256 and missing days; `events.csv` and `research_report.json` are reproducible results.
- Public GitHub Actions artifact retention: one day. No private MT5 data or credentials are copied here.
- Dukascopy data is third-party data. Do not silently claim redistribution rights or upload it permanently to public source control.

## Known limitations
- This version intentionally uses bid close/TK only. It does not reconstruct MT5 quote microstructure or tick-side trade simulation.
- Contiguous segmentation avoids interpolation, at the cost of excluding events near feed gaps.
- Archived MT5 results and Q25 historical outcome claims are not transferred into this variant.
- Any comparison across feeds requires a future separate harmonized study.

## 2026-10-14 access finding
Direct daily Dukascopy .bi5 URL returned HTTP 503 from the GitHub runner. The documented public archive at kevingtlin/Market-Data-Lab is used as a **fallback provider**. Its declared Dukascopy provenance is not independently cryptographically confirmed. Source counts and event populations must remain separate from direct Dukascopy and MT5 evidence.

## Quality gate added after observing raw archive (2026-10-14)
- Initial unfiltered ML run must NOT be used for research inference: 61,603 / 230,813 rows have O=H=L=C; weekend quotes include multiple 2-3 day static blocks. Those flat-filled intervals artificially join non-trading sessions and contaminate horizons.
- Deterministic source QC, frozen **before re-training**: exclude every run of 5 or more consecutive O=H=L=C 1-minute candles. Remove their timestamps, never forward-fill; split event windows at resulting gaps. Five-minute threshold is a conservative feed-integrity heuristic, not trained or optimized for labels.
- Run `sanitize.py` after `mirror_source.py` and pass `xauusd_m1_bid_quality_checked.csv` to `analyze.py`.
- Versioned `quality_audit.json` reports how many bars and flat segments were removed. The original unclean run is FAIL for research evidence (pipeline execution PASS only).
