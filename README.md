# Technical Stock Analysis (TAK)

A keyless stock-analysis engine that operationalizes the classic German textbook *Technische Aktienanalyse* (Welcker & Audörsch, Saarland University / Charité Berlin, 1990s) as runnable Python:

- **Moving averages per §4.1** — 38 / 100 / 200 trading-day lines with the book's crossover buy/sell rule
- **Gaps per §5** — break-away and common gap detection over daily candles
- **Point & Figure per §6** (simplified box model) — column direction, reversal on one box height, buy signal on breaking the previous up-swing peak (§6.1), sell symmetrically
- **Candle rules per §7** — explicit if–then decisions from the book's worked solutions (Hammer / Hanging Man per §7.3.2.5, Dark Cloud Cover combination)

Prices come from Yahoo Finance's public chart API (`data_fetch.py`) and are cached locally as CSV. No API keys required; stdlib only. Built to be used by an agent skill (`SKILL.md`): it fixes the strict obligations (no invented data, language mirrors request language, mandatory disclaimer) and a complete report pattern combining fundamentals + technicals + news.

## Layout

```
├── SKILL.md                     # Skill definition: commands, obligations, report pattern
├── README.md
├── LICENSE                      # MIT — Felix Morocutti (https://github.com/FelixM2011)
├── data_fetch.py                # OHLCV fetch + local cache (Yahoo v8 chart API)
├── tak_analyze.py               # TAK engine: MAs, gaps, Point & Figure, candle signals → JSON report
└── references/
    └── signals-and-sources.md   # Rule definitions and their chapter sources in the book
```

## Quick start

```bash
# refresh price cache (1 year ≈ ~250 daily candles — enough for all three MA lines)
python3 data_fetch.py MSFT --range=j

# run the full technical analysis; writes tak_result_MSFT.json
python3 tak_analyze.py MSFT --range=j
```

Available ranges: `wk` (1 month), `m` (3 months), `q` (6 months), `h` (YTD), `j` (1 year, default), `2j`, `5j`, `10j`, `max`. The JSON report contains every MA value/position/crossover, all gaps in the window, today's candle signals and the last ten P&F column-break signals.

### RSI(14) / ATR(14) from the cached CSV

The skill workflow supplements the TAK output with RSI(14) and ATR(14), both using Wilder smoothing over `ohlcv_1y_daily.csv`: seed the 14-period averages of gains/losses (RSI) and true ranges (ATR) from the first 14 candles, then iterate `avg = (prev_avg * 13 + new_value) / 14`. RSI(14) maps to `100 − 100/(1+avg_gain/avg_loss)`, ATR is the smoothed true range in price points.

## Cache location

- Default: `~/.hermes/cache/data/invest/<TICKER>/` — override with the environment variable `HERMES_INVEST_DATA`.
- Files per range: `ohlcv_<range>_daily.csv`, plus a `meta.json` (source, fetch time, currency, exchange). Caches older than 15 minutes are refetched automatically.

## Design notes

- Rule faithfulness over modernization: the signal rules are transcribed directly from the book's wording and worked examples — including their deliberate deviations from standard Nison conventions (see [references/signals-and-sources.md](references/signals-and-sources.md)).
- The Point & Figure engine uses a percentage-of-price box unit with reversal = one box height. It is **not** pixel-perfect P&F but faithful to the book's signal semantics: exactly one signal per impulse on breaking the previous swing's element.
- `tak_analyze.py` never invents data: when the candle history is too short for a line (e.g. 200-day MA with only ~120 candles), it reports "insufficient data" instead of truncating or padding.

## License

MIT — see [LICENSE](LICENSE). Not investment advice; all outputs are technical signals without any guarantee. Do your own due diligence.
