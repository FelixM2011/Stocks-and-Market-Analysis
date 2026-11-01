#!/usr/bin/env python3
"""DataFetch — Tages-Kerzen (OHLCV) von der Yahoo-Chart-API holen und cachen.

Cache liegt unter ~/.hermes/cache/data/invest/<TICKER>/ohlcv_daily.csv
(umsetzbar: Umgebungsvariable HERMES_INVEST_DATA).
Keine Abhaengigkeiten — nur stdlib (urllib, json, csv).

Nutzung:
    python3 data_fetch.py SAP.DE            # 1 Jahr Tageskurse
    python3 data_fetch.py SAP.BY --range 10y
    python3 data_fetch.py AAPL --interval 5d

Yahoo-URLs (geprueft):
    https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={r}&interval={i}
    https://query1.finance.yahoo.com/v7/finance/quote?symbols={sym}   (aktueller Kurs)
    https://query1.finance.yahoo.com/v6/finance/search?q={sym}       (Symbol-/Wertszeugsuche)
"""

import csv
import json
import os
import sys
import time
import urllib.request
import urllib.error

DATA_DIR = os.path.expanduser(
    os.environ.get("HERMES_INVEST_DATA", "~/.hermes/cache/data/invest"))
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
RANGES = {  # Yahoo-range-Parameter
    "wk": "1mo", "m": "3mo", "q": "6mo", "h": "ytd",
    "j": "1y", "2j": "2y", "5j": "5y", "10j": "10y",
    "max": "max",  # plus Sonderwerte "3mo", "6mo", ... direkt
}


def _get_json(url, params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(url + sep + q, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:  # ⊂ URLError — zuerst fangen (Statuscode)
        print("Yahoo antwortet mit HTTP %d — Symbol/URL prüfen." % e.code, file=sys.stderr)
        return None
    except (urllib.error.URLError, TimeoutError):  # DNS, Erreichbarkeit, Zeitüberschreitung
        print("Netzwerkfehler bei der Yahoo-Abfrage (Erreichbarkeit/Timeout). "
              "Bitte später erneut versuchen.", file=sys.stderr)
        return None


def search_symbol(query):
    """Wertszeug-Suche ueber die Yahoo-Search-API. Listet Treffer."""
    raw = _get_json("https://query1.finance.yahoo.com/v6/finance/search",
                   {"q": query, "quotesCount": "8", "newsCount": "0"})  # None bei Fehler (bereits gemeldet)
    res = (raw or {}).get("quotes") or []
    out = []
    for q in res:
        out.append({
            "symbol": q.get("symbol"),
            "name": (q.get("shortName") or q.get("longName") or "")[:60],
            "typ": q.get("quoteType") or "?",
            "exchange": q.get("exchDisp") or q.get("exch") or "",
            "kurs": q.get("regularMarketPrice"),
        })
    return out


def fetch_ohlcv(symbol, range_key="1y", interval="1d"):
    """Tages-OHLCV holen und ins Cache legen.

    Liefert (zeilen, pfade_dict) — zeilen sind Dicts mit den Feldern
    timestamp(iso), open, high, low, close, volume, adj_close.
    Existiert das Cache-CSV fuer diese Kombination bereits < 15 min alt,
    wird es geladen; sonst neu geholt.
    """
    rng = RANGES.get(range_key, range_key)
    dir_sym = os.path.join(DATA_DIR, symbol.replace("/", "_"))
    os.makedirs(dir_sym, exist_ok=True)
    # Cache je Range getrennt — sonst würde z. B. ein 'j'-Aufruf eine 'max'-Datei überschreiben (und umgekehrt).
    csv_name = "ohlcv_%s_daily.csv" % rng if interval == "1d" else "ohlcv_%s_%s.csv" % (rng, interval)
    csv_path = os.path.join(dir_sym, csv_name)

    stale = not os.path.exists(csv_path) or \
        (time.time() - os.path.getmtime(csv_path)) > 900

    meta_json = {"symbol": symbol, "range": rng, "interval": interval}

    if not stale and interval == "1d":
        zeilen = load_csv(csv_path)
        if len(zeilen) >= 2:
            meta_json["quelle"] = "cache"
            with open(os.path.join(dir_sym, "meta.json"), "w") as f:
                json.dump(meta_json, f)
            return zeilen, {"csv": csv_path, "symbol_dir": dir_sym}

    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + symbol)
    raw = _get_json(url, {"range": rng, "interval": interval})  # None bei Netzwerk-/HTTP-Fehler (bereits gemeldet)
    if not isinstance(raw, dict):
        return [], {"csv": None, "symbol_dir": dir_sym}

    result = ((raw or {}).get("chart") or {}).get("result") or []
    if not result:  # u. a. bei ungültigem Symbol {…,"result":null} → leeres Resultat
        print("Yahoo liefert für %s kein Chart-Resultat — Symbol prüfen." % symbol, file=sys.stderr)
        return [], {"csv": None, "symbol_dir": dir_sym}
    d = result[0]

    ts_list = d.get("timestamp") or []
    q = d.get("indicators", {}).get("quote", [{}])[0] or {}
    meta = d.get("meta", {})

    zeilen = []
    for i, t in enumerate(ts_list):
        o, h, l, c, v = (q[k][i] if q.get(k) else None
                          for k in ("open", "high", "low", "close", "volume"))
        adj = d.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose") or []
        a = adj[i] if i < len(adj) and adj[i] is not None else c
        # Null-Werte bei Feiertagen ausschliessen
        if o is None or h is None or l is None or c is None:
            continue
        zeilen.append({
            "timestamp": time.strftime("%Y-%m-%d", time.gmtime(t)),
            "open": round(float(o), 4), "high": round(float(h), 4),
            "low": round(float(l), 4), "close": round(float(c), 4),
            "volume": int(v) if v else 0,
            "adj_close": round(float(a), 4),
        })

    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(zeilen[0].keys()) if zeilen else
                           ["timestamp", "open", "high", "low", "close", "volume", "adj_close"])
        w.writeheader()
        w.writerows(zeilen)

    meta_json.update({
        "quelle": "yahoo_v8chart",
        "abgerufen_zum": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "letzte_notierung": meta.get("regularMarketPrice"),
        "waehrung": meta.get("currency"),
        "borsen_name": meta.get("fullExchangeName") or meta.get("exchangeName"),
    })
    with open(os.path.join(dir_sym, "meta.json"), "w") as f:
        json.dump(meta_json, f)
    return zeilen, {"csv": csv_path, "symbol_dir": dir_sym}


def load_csv(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                for k in ("open", "high", "low", "close"):
                    row[k] = float(row[k])
                row["volume"] = int(float(row.get("volume") or 0))
                row["adj_close"] = float(row.get("adj_close") or row["close"])
            except (ValueError, KeyError):
                continue
            out.append(row)
    return out


if __name__ == "__main__":
    args = [a.lower() if a in ("ytd", "max") else a for a in sys.argv[1:]]
    symbol = None
    rng, ivl = "1y", "1d"
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--range="):
            rng = a.split("=", 1)[1]
        elif a == "--interval":
            i += 1
            ivl = args[i]
        else:
            symbol = a
        i += 1
    if not symbol:
        print("Benutzung: data_fetch.py ZEICHEN --range=1y|2j|5j|10j|max [--interval 1d]")
        sys.exit(4)
    zeilen, p = fetch_ohlcv(symbol.upper() if "." not in symbol else symbol, rng, ivl)
    print(f"{symbol}: {len(zeilen)} Kerzen; CSV: {p.get('csv') or '(keine)'}")
    for z in zeilen[-3:]:
        print(" ", z["timestamp"], f"O={z['open']} H={z['high']} L={z['low']} "
                                  f"C={z['close']} V={z['volume']:,}")
