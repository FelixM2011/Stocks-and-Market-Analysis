---
name: technical-stock-analysis
description: "Use when a stock/ISIN analysis request comes in (e.g. 'analyse XYZ'). Runs the TAK engine bundled with this skill and produces a fundamental + technical report."
version: 1.0.0
author: Felix Morocutti https://github.com/FelixM2011
license: MIT
metadata:
  hermes:
    tags: [stocks, technical-analysis, point-and-figure, candlesticks]
    requires_toolsets: [web, terminal]
---

# Technical Stock Analysis

Keyless stock-price analysis built on the classic German textbook *Technische Aktienanalyse* (Welcker & Audörsch): moving averages per §4.1, break-away/away gaps per §5, Point-and-Figure columns per §6, and explicit candle if–then rules per §7 — plus fundamental data and news for a complete ticker report.

## Commands (run from this skill's folder)
```bash
python3 tak_analyze.py <TICKER> --range=j        # 38/100/200-day MAs, gaps, P&F column, candle signals
python3 data_fetch.py <TICKER> --range=j         # refresh price cache (1y ≈ ~250 daily bars)
```
- Console summary + JSON report: `tak_result_<TICKER>.json` (written next to the scripts).
- OHLCV CSV cache: `~/.hermes/cache/data/invest/<TICKER>/ohlcv_1y_daily.csv` (override directory via the environment variable `HERMES_INVEST_DATA`).

## Symbol resolution
Resolve ISIN → ticker unambiguously **before** loading data. Known mappings, among others: US5949181045 = MSFT, US02079K3059 = GOOGL/Alphabet A (Class C: GOOG), US88160R1017 = PLTR. Only ever use tickers that were actually loaded; when in doubt resolve via the Yahoo search API (`data_fetch.search_symbol`) instead of guessing.

## Obligations (strict, no exceptions)
1. **No invented data.** Every number in the report must come from a real fetch within the same run (chart API, `tak_analyze.py` JSON, statistics page, news RSS). No price, metric, or date without verification — and if a fetch fails: retry exactly once with a shorter query; after that mark the item "not available". Never fill in or interpolate missing values.
2. **Answer language = request language.** German question → German report (buy/sell labels, bull/bear). English question → English report, etc. Technical terms may stay in their original language.
3. **Disclaimer always as the last line of the report:**
   > This is not investment advice. All data without guarantee — please do your own due diligence.

## Report structure (fixed pattern)
1. **KPI focus** (table): closing price + timestamp, 52-week high/low, market cap, P/E / forward P/E, revenue TTM, FCF, dividend yield — each with its source.
2. **Signal picture from `tak_result_<TICKER>.json`**: MA position per line (bull/bear region), latest gap + direction, P&F column + last signal level, candle signal for today (if any). Supplement RSI(14) and ATR(14) from the cached CSV. See [references/signals-and-sources.md](references/signals-and-sources.md) for the exact rule definitions.
3. **News & catalysts**: 3–6 relevant items from roughly the last 1–2 weeks with links and dates; name the trigger of recent price moves explicitly where identifiable.
4. **Technical zones** (table): resistance above + next buy-trigger level; support directly under the current price (nearest MA line); further support below. All levels must be derived from real data only.
5. **Concluding judgment**: 3–5 sentences balancing fundamentals against technicals, stating the disposition (buy / hold / reduce) and the exact level that would change it.

## Source set per run (parallel where possible)
- Prices/technicals: `tak_analyze.py` + RSI(14)/ATR(14) computed from the cached CSV (local).
- Fundamentals: `https://stockanalysis.com/stocks/<ticker>/statistics/` (market cap, P/E, revenue TTM, FCF, dividend yield).
- News: Google News RSS (`news.google.com/rss/search?q=<TICKER>`) or web search; on an empty result, retry once with a shorter query.

## Notes on the rule engine
The signal rules are transcribed 1:1 from the textbook (German original), deliberately **not** normalized to modern Nison conventions — e.g. per §7.3.2.5 the "Hanging Man" is a parasol with a long *upper* shadow after an up-move, and the point-and-figure buy signal fires once per impulse on breaking the previous swing's peak (§6.1). Full mappings are in [references/signals-and-sources.md](references/signals-and-sources.md).
