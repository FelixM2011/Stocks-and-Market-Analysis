# Signal rules and their source chapters

Reference mapping between `tak_analyze.py` engine sections, the signals it emits, and their exact home in *Technische Aktienanalyse* (Welcker & Audörsch). The rules are transcribed from the book's wording — including its deliberate deviations from modern Nison conventions. Do not "modernize" a rule without re-checking the original passage; internal consistency with the book beats external orthodoxy.

## 1. Moving averages (§4.1, ch. 4 — general market analysis)

The book states (paraphrase, §4.1): compute **38-day**, **100-day** or **200-day** moving averages; "days" means *trading days*, so the three correspond to roughly two months, half a year and one year.

Engine rules (`kap_gleitende`):
- `lage = above`: price above its MA → "Hausse-Region" (bull region). Below → bearish side of that line.
- **Crossover buy**: close crosses the 38/100/200-day MA from below to above over a single bar ⇒ buy signal, "price rises quickly".
- **Crossover sell**: cross from above to below ⇒ sell signal, "enters a phase of decline".
- Detection window: last 5 days. If fewer than `n` candles are available for an `n`-day average, the report says "insufficient data — increase range" instead of shortening or padding the line.

## 2. Gaps (§5 — candlestick/bar-chart analysis)

A **gap** exists when two consecutive daily candles leave no traded price between them:
- Gap up: low(today) > high(yesterday), width = `low_today/high_yesterday − 1`.
- Gap down (high-hole): high(today) < low(yesterday), width = the mirror formula.

Both break-away and common gaps are reported; the report surfaces count in window + latest gap with date, direction and width %. Interpretation (break-out context of a trend vs. continuation of an impulse) is a reading step for the agent, not part of the engine output.

## 3. Point & Figure (§6 — market theory of P&F charts)

Engine model (`kap_point_figure`, simplified but rule-faithful):
- **Box unit**: default `box_pct` = 0.5 % of the current price (percentage box, stand-in for a fixed "Kästcheneinheit" independent of absolute share price).
- **Reversal** = one full box height against the current column extreme (the book's reversal condition) ⇒ turn to an opposite-direction column at that box.
- **Buy signal (§6.1, verbatim in spirit)**: "A buy signal exists when, during an upward move, the highest point of the last preceding upward move is exceeded." → signal fires **once per impulse**, on breaking the previous up-swing peak (`prev_peak`). It does *not* fire on every box step.
- **Sell**: symmetric — breaking below the low of the previous completed down-move (`prev_trough`), once per impulse.
- The initial trend (§6.2: at chart start it is "still unclear which direction" it will take) provides no signal — entry only.

Report fields: current column direction (bull/bear), column high/low, and the last 10 signals with date + level. This model intentionally ignores vertical gaps and three-point-reversal micro-details; it reproduces the book's *signal semantics*, not pixel-perfect chart construction.

## 4. Candlestick if–then rules (§7 — Japanese candle analysis)

Color convention of this engine (matches the book): **white/bullish** = close above open, **black/bearish** = reverse. Signal color words in messages follow that convention; a Western bullish/candle-color palette is not used because the book's phrasing defines it.
- Current bar state: `body(c) > 0` ⇒ white; `< 0` ⇒ black. A very small body relative to span (doji-style, absolute-body below ~25 % of the full range) carries no color claim (§7 doji paragraph).

Trend helper (`trend_dir`, last 5 steps): a direction is claimed only if both a strict majority of daily deltas agree and the net change over those 5 bars agrees. Zig-zag sequences without a clear trend yield "no trend" — protecting the rules below from firing on noise. This exact formulation (majority *and* net) is not printed in the book; it is a conservative operationalization chosen so "after an up/downward move" remains interpretable.

Single-candle and combination rules implemented (`kap_kerzen`, evaluated today only):
1. **Hammer / white sunrise — buy (book hammer example)**: after a downtrend, a bar with lower shadow ≥ 2× its body and a small upper shadow.
2. **Hanging Man / parasol — sell (§7.3.2.5)**: the book defines it as "a parasol standing above the price curve *after an upward move*" — i.e. long **upper** shadow with close near open (no lower-shadow requirement). This is a mirror-reading of Nison's classical Hanging Man (long *lower* shadow); keep the book version here, flag divergences explicitly if you compare against other literature.
3. **Dark Cloud Cover — sell**: previous day long white body, today black opening above midpoint of yesterday's body and closing below that midpoint.

Other §7 patterns (engulfing stars, three crows/clouds, doji families) are defined in the book but not encoded yet; treat "no signal" from `kap_kerzen` as "the current day does not match any implemented explicit rule", not "no relevant pattern exists". Doji detection uses an approx. 0.25 body/span threshold — a working approximation, not a fixed book constant.

## 5. RSI(14) and ATR(14) (supplement, not TAK)

Taken from the cached CSV `ohlcv_<range>_daily.csv` (see README): Wilder smoothing, seed = simple average of the first 14 gains/losses or true ranges, then `avg_new = (avg_prev * 13 + value) / 14`. Report with one decimal; ATR in price points. These are standard indicators and are not attributed to any chapter in the book — keep them separated from §4–§7 output when writing reports.

## General handling rules for the agent
- Engine verdicts (`gd_kap4.lage`, gaps, `p_and_f_kap6.signale`, `kerzen_kap7.signal_heute`) are **facts**; interpretation (e.g. "this is a break-away gap in an uptrend") belongs to you as analyst and must not overwrite the raw JSON values inside the report tables.
- When data is insufficient for a rule (too few candles), reproduce the `hinweis` field verbatim rather than guessing a level.
