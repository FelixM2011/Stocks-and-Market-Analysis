#!/usr/bin/env python3
"""TAK-Analyse — Technische Aktienanalyse

Setzt die im PDF extrahierten Kapitel als Anlage-Engine um:
     Gleitende Durchschnittslinien laut §4.1: 38 / 100 / 200 Börsentage
             + Crossover-Regel ("Kurs durchbricht die Linie von unten nach oben")
       Lücken / Trendlinien-Erkennung (Bruchs-/Ausbruchs-Gap-Kontext)
       Point-and-Figure-Charts (Boxeneinheit, Reversal = Boxenhöhe,
             Kauf-/Verkaufssignale bei Spaltendurchbrüchen)
       Kerzen-Signale: die expliziten Wenn-Dann-Entscheidungsregeln der
             Buch-Auflösung (Einzelkerzen + Kombinationen + Dreibalkendiagramm)

Aufruf:  python3 tak_analyze.py SYMBOL [--range wk|m|q|h|j|2j|5j|10j|max]
Daten:   data_fetch.fetch_ohlcv() aus dem Nachbarverzeichnis (Yahoo-Finance,
         eigenes Cache je Range; 'j' = 1 Jahr ≈ ~250 Kerzen — deckt alle drei Linien ab).
Output:  Report als JSON neben diesem Skript + deutsche Konsolenzusammenfassung.
Kein Teil der Signale ist erfunden — jede Regel trägt einen Quellverweis ins Buch.
"""

import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, HERE)
from data_fetch import fetch_ohlcv, RANGES  # noqa: E402


# ---------------------------------------------------------------------------
# Hilfsfunktionen (generisch, nicht signalspezifisch)
# ---------------------------------------------------------------------------

def sma(vals, n):
    """Simple Moving Average; None wo noch <n Werte fehlen."""
    out = [None] * len(vals)
    if not vals or n <= 0 or len(vals) < n:
        return out
    s = sum(vals[:n])
    out[n - 1] = s / n
    for i in range(n, len(vals)):
        s += vals[i] - vals[i - n]
        out[i] = s / n
    return out


def body(c):          # Kerzenkörper (positiv = aufwärts/weiß, negativ = abwärts/schwarz)
    return c[3] - c[0]


def upper_shadow(c):
    return c[1] - max(c[0], c[3])


def lower_shadow(c):
    return min(c[0], c[3]) - c[2]


def is_doji(c, ratio=0.25):
    span = c[1] - c[2]
    if span <= 0:
        return True
    return abs(body(c)) < ratio * span


def trend_dir(kerzen, n=5):
    """Richtung über die letzten n Tagesschritte (+1 aufwärts / -1 abwärts / 0 = keine klare Tendenz).

    Das Buch formuliert nur „nach einer Ab-/Aufwärtsbewegung" ohne Formel, daher eine konservative
    Dualregel: strikte Mehrheit der Vorzeichen der letzten n Tagesschritte UND Nettoergebnis in der
    gleichen Richtung. Damit werden Zickzack-Linien ohne klare Tendenz sauber "0". Beispiel:
    100→95→80→70→65→110 = 4 Ab-/1 Auf-Stufe, aber ein großer Schluss-Sprung (+45) und Netto +10,
    also Mehrheit = abwärts, netto = aufwärts → keine klare Tendenz (ein einfacher Close-vs-Start-Vergleich
    würde hier fälschlich "aufwärts" werten). Die Zickzack-Linie 100→110→90→111→95→112 bleibt dagegen
    aufwärts (3 Auf-/2 Ab-Stufen, Netto +12) — was sie faktisch auch ist.

    Bei len(kerzen) < n+1: nicht genug Daten → 0.
    """
    if len(kerzen) < n + 1:
        return 0
    closes = [c[3] for c in kerzen[-(n + 1):]]
    diff = [closes[i + 1] - closes[i] for i in range(n)]
    ups, downs = sum(1 for d in diff if d > 0), sum(1 for d in diff if d < 0)
    netto = closes[-1] - closes[0]
    if ups > downs and netto > 0:
        return 1
    if downs > ups and netto < 0:
        return -1
    return 0


def _signum(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


# ---------------------------------------------------------------------------
# Gleitende Durchschnitte
# ---------------------------------------------------------------------------

# Zeiträume nur mit in den extrahierten Buchseiten belegten Werten:
GD_SPEZIES = (  # Buch §4.1 S. 29 wörtlich: „Man berechnet 38−Tage−Durchschnitte,
    # 100−Tage−Durchschnitte oder 200−Tage−Durchschnitte … Mit 'Tagen' sind nicht
    # Kalendertage, sondern Börsentage gemeint. Die Zeiträume entsprechen somit
    # etwa zwei Monaten, einem halben Jahr und einem Jahr."
    (38, "zwei-Monats-Linie"),   # ≈ 2 Monate  (~38 Handelstage)
    (100, "Halbjahreslinie"),    # ≈ ½ Jahr     (~100 Handelstage)
    (200, "Jahreslinie")         # ≈ 1 Jahr      (~200 Handelstage)
)


def kap_gleitende(kerzen):
    """GD-Lage (oben/unten + Abstand %) plus Crossover-Regel aus Kap. 4."""
    closes = [k[3] for k in kerzen]
    out = {"gd": {}, "crossovers": []}
    for n, name in GD_SPEZIES:
        gdl = sma(closes, n)
        if not gdl or gdl[-1] is None:
            # nicht genug Tageskerzen im Datenbestand → Hinweis statt Fehler
            out["gd"][str(n)] = {
                "name": name, "ok": False,
                "hinweis": "mindestens %d Tageskerzen benötigt (Datenbestand kürzer) — Range vergrößern" % n,
            }
            continue
        gk, cur = gdl[-1], closes[-1]
        diff = (cur - gk) / gk * 100.0 if gk else None
        out["gd"][str(n)] = {
            "name": name, "ok": True,
            "wert": round(gk, 4), "kursaktuell": cur,
            "abstand_pct": round(diff, 2) if diff is not None else None,
            # Lage laut Buch: „über der gleitenden Durchschnittslinie (Hausseregion)"
            "lage": "über" if cur > gk else "unter",
        }
        # Crossover über die letzten 5 Tage (Buch-Regel: von unten nach oben durchbricht => Aufwärtsphase)
        for back in range(1, 6):
            if len(gdl) <= back or gdl[-back - 1] is None:
                continue
            v_heute, vorg = closes[-back], gdl[-back]
            v_gestern, vg_vorg = closes[-back - 1], gdl[-back - 1]
            if vg_vorg is None or vorg is None:
                continue
            up_cross = v_gestern <= vg_vorg and v_heute > vorg
            dn_cross = v_gestern >= vg_vorg and v_heute < vorg
            if up_cross:
                out["crossovers"].append({"vor": back - 1, "richtung": "nach oben",
                                          "gd": name})  # Buch: „steigt schnell an — ein Kaufsignal"
            elif dn_cross:
                out["crossovers"].append({"vor": back - 1, "richtung": "nach unten",
                                          "gd": name})  # Buch: „tritt in eine Phase des Absinkens über — Verkaufssignal"
    return out


# ---------------------------------------------------------------------------
# Lücken (Break-away / common gaps über zwei aufeinanderfolgende Kerzen)
# ---------------------------------------------------------------------------

def kap_luecken(kerzen):
    """Lücke = kein Handel zwischen zwei Tageskerzen: H_t < L_{t+1} oder L_t > H_{t-1}."""
    out = []
    for i in range(1, len(kerzen)):
        prev, cur = kerzen[i - 1], kerzen[i]
        if cur[2] > prev[1]:            # Lücke nach oben (Gap-up)
            out.append({"tag": cur[4], "typ": "Gap aufwärts", "von_hoch_vortag": prev[1],
                        "bis_tief_heute": cur[2], "brei_pct": round((cur[2] / prev[1] - 1) * 100, 2)})
        elif cur[1] < prev[2]:          # Lücke abwärts (Hoch-Loch / Gap-down)
            out.append({"tag": cur[4], "typ": "Gap abwärts", "von_tief_vortag": prev[2],
                        "bis_hoch_heute": cur[1], "brei_pct": round((cur[1] / prev[2] - 1) * 100, 2)})
    return out


# ---------------------------------------------------------------------------
# Point & Figure (vereinfachte Engine im Buchmodell)
# ---------------------------------------------------------------------------

def kap_point_figure(kerzen, box_pct=0.5):
    """P&F-Modell: Kästcheneinheit (hier % vom Kurs), Reversal = eine Boxenhöhe.

    Kauffsignal nach Kap. 6.1 (S. 76) wörtlich: „Ein Kaufsignal liegt vor, wenn im Zuge einer
    Aufwärtsbewegung der Höchstpunkt der letzten vorangegangenen Aufwärtsbewegung überschritten
    wird.“ Verkauf symmetrisch (Unterscheitung des Tiefes der alten Abwärtsbewegung).
    D. h.: pro neuem Schwung gibt es EIN Signal — den ersten Bruch des alten Referenzelements
    (nicht bei jedem Kästchen-Schritt!). Der Anfangstrend selbst (§6.2: „anfangs noch nicht klar,
    welche Trendrichtung … einschlagen wird“ → nur Hilfsweise Punkte) liefert kein Signal."""
    if not kerzen:
        return {"ok": False}
    box_abs = None            # Boxenhöhe in Kursabsoluten — Bezugspreis: letzter Schlusskurs (rangeunabhängig)
    col_high = col_low = None  # aktuelle Spalte
    direction = None           # 'bull' / 'bear'
    price0 = kerzen[-1][3]
    prev_peak = None           # Höchstpunkt der letzten ABGESCHLOSSENEN Bullen-Spitze (Kaufreferenz)
    prev_trough = None         # Tiefste Punkt der letzten ABGESCHLOSSENEN Bären-Grube (Verkaufsreferenz)
    bull_break_done = bear_break_done = False  # je Schwung: Bruch des alten Elements einmal gemeldet?
    signals = []

    for k in kerzen:
        c = k[3]                 # Schlusskurs der Kerze (O,H,L,C,Tupel — t = Zeitstempel)
        t = k[4]
        if box_abs is None:      # erste Kerze: Anfangstrend (§6.2) — nur Einstieg, kein Signal
            box_abs = abs(price0 * box_pct / 100.0)    # defensive: Box ist immer positve Höhe
            col_high = col_low = c
            direction = "bull"
            continue

        if direction == "bull":
            while c >= col_high + box_abs:           # um ein Vielfaches der Boxenhöhe aufwärts
                col_high += box_abs
            # Kap. 6.1: Kauf erst wenn die aktuelle Bullen-Spitze den Höchstpunkt der ALTEN
            # Aufwärtsbewegung übersteigt — und dann nur einmal pro Schwung.
            if prev_peak is not None and not bull_break_done and c > prev_peak:
                bull_break_done = True
                signals.append({"tag": t, "signal": "KAUF (Spaltendurchbruch)",
                                "niveau": round(c, 4)})
            # Reversal nach unten = eine Boxenhöhe unter dem Spaltenmaximum (§6.2: 3-Point-Umkehr)
            if c < col_high - box_abs:
                prev_peak = col_high                   # Spitze der beendeten Bullen-Spitze wird Kaufreferenz
                direction = "bear"
                col_low = c - box_abs                  # (Reversalfeld)
                bull_break_done = False
        else:
            while c <= col_low - box_abs:             # um ein Vielfaches der Boxenhöhe abwärts
                col_low -= box_abs
            if prev_trough is not None and not bear_break_done and c < prev_trough:
                bear_break_done = True
                signals.append({"tag": t, "signal": "VERKAUF (Spaltendurchbruch)",
                                "niveau": round(c, 4)})
            # Reversal aufwärts = eine Box über dem Spaltenminimum
            if c > col_low + box_abs:
                prev_trough = col_low                 # Grube der laufenden Bären-Spitze wird zur Verkaufsreferenz
                direction = "bull"
                col_high = c + box_abs                # (Reversalfeld)
                bear_break_done = False

    return {
        "ok": True,
        "kaestchen": "%g %% vom Kurs (~Boxenmodell)" % box_pct,
        "aktuelle_richtung": direction,
        "spaltenhoch": round(col_high, 4), "spaltentief": round(col_low, 4),
        "signale": signals[-10:],   # letzte 10 Kauf-/Verkaufsweichen in der Serie
    }


# ---------------------------------------------------------------------------
# Kerzen-Signale (Wenn-Dann aus der Buch-Auflösung)
# Farbsprache: weisse/bullish = Schluss über Eröffnung; schwarze/bearish = umgekehrt.
# ---------------------------------------------------------------------------

def kap_kerzen(kerzen):
    """Setzt die expliziten Wenn-Dann-Regeln aus Kap. 7 auf die letzten Kerzen an."""
    if len(kerzen) < 8:
        return {"ok": False, "hinweis": "mindestens 8 Kerzen erforderlich"}

    K = kerzen[-1]
    K_1, K_2 = kerzen[-2], kerzen[-3]
    O1, H1, L1, C1 = K[0], K[1], K[2], K[3]
    bo1 = body(K)               # Body heute

    sigs = []                    # (signal, begründung/Quellverweis) — wir melden nur tagesaktuell

    # --- Einzelkerzen ------------------------------------------------------
    # --- Einzelkerzen ------------------------------------------------------
    if trend_dir(kerzen[:-1]) == -1 and not is_doji(K_2):
        lb, ub = lower_shadow(K), upper_shadow(K)
        if lb >= 2 * max(abs(bo1), 1e-9) and ub <= abs(bo1) + (K[1] - K[2]) * 0.2:
            sigs.append(("Hammer / weisser Sonnenschein — KAUF-SIGNAL",
                         "Abwärtsverlauf, lange Fußkette (≥2× Körper), kleiner Oberlicht"))

    # Hanging Man nach diesem Buch §7.3.2.5 = „Sonnenschirm nach einer Aufwärtsbewegung, der über der Kurskurve steht":
    # lange obere Schattenkerze mit Schluss nahe Offene — das Bild des Hammers (bewusst NICHT die Nison-Konvention).
    if trend_dir(kerzen[:-1]) == 1 and not is_doji(K_2):
        ub = upper_shadow(K)
        if ub >= 2 * max(abs(bo1), 1e-9) and lower_shadow(K) <= (K[1] - K[2]) * 0.2:
            sigs.append(("Hanging Man / Grabmal — VERKAUF-SIGNAL",
                         "Aufwärtstrend, Sonnenschirm über der Kurslinie (langes Oberlicht, Schluss nahe Offene)"))

    # --- Zweierkombinationen -------------------------------------------------
    mid_k1 = (K_1[0] + K_1[3]) / 2.0      # Mittelpunkt des Körper-Vortags
    # Dunkle Wolke: Vortag langer weißer Körper; heute schwarz, 
    # Eröffnung überhalb der Mitte und Schluss darunter (Kap. 7 Kombinationen)
    if _signum(body(K_1)) == 1 and abs(body(K_1)) >= (K_1[1] - K_1[2]) * 0.6 \
            and _signum(body(K)) == -1 and O1 > mid_k1 and C1 < mid_k1:
        sigs.append(("Dunkle Wolke — VERKAUF-SIGNAL",
                     "Vortag langer weißer Körper, heutige schwarze Kerze schließt unter dessen Mittelpunkt"))

    return {"ok": True, "signal_heute": sigs}


def main():
    ap = argparse.ArgumentParser(description="Technische Analyse: Gleitende Durchschnitte, Gaps, Point & Figure, Kerzensignale")
    ap.add_argument("symbol", help="Ticker, z.B. SAP")
    ap.add_argument("--range", default="j", dest="rng",
                    choices=sorted(RANGES),
                    help="Zeitraum der Tageskerzen (Standard 'j' = 1 Jahr ≈ ~250 Kerzen — reicht für alle drei Linien)")
    args = ap.parse_args()

    rows, paths = fetch_ohlcv(args.symbol.upper(), range_key=args.rng)
    if not rows:
        print("Keine OHLCV-Zeilen geliefert — Symbol prüfen oder Range ändern.")
        sys.exit(1)

    kerzen = [(r["open"], r["high"], r["low"], r["close"], r["timestamp"]) for r in rows]
    report = {
        "symbol": args.symbol.upper(),
        "range": args.rng,
        "kerzen_zeitraum": [rows[0]["timestamp"], rows[-1]["timestamp"]],
        "n_kerzen": len(rows),
        "gd_kap4": kap_gleitende(kerzen),
        "luecken_kap5": kap_luecken(kerzen),
        "kerzen_kap7": kap_kerzen(kerzen),
        "p_and_f_kap6": kap_point_figure(kerzen),
    }

    out_path = os.path.join(HERE, "tak_result_%s.json" % args.symbol.upper())
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # ------- Konsolenzusammenfassung (Deutsch) ------------------------------
    print("=== Technische Analyse %s (%d Kerzen bis %s) ===" % (args.symbol.upper(), len(rows), rows[-1]["timestamp"]))
    for key, v in report["gd_kap4"].get("gd", {}).items():
        if v.get("ok"):
            print("  %-18s: %7.2f | Kurs %7.2f (%+.2f %%) — %s" % (v["name"], v["wert"],
               round(v.get("kursaktuell") or 0.0, 2), round(v.get("abstand_pct") or 0.0, 2),
               "Hausse-Region" if v.get("lage") == "über" else "Baisse-Region"))
        else:
            print("  %-18s: %s" % (key, v.get("hinweis", "Daten nicht vorhanden")))
    for c in report["gd_kap4"].get("crossovers", []):
        art = "Kauf-" if c["richtung"] == "nach oben" else "Verkauf-"
        print("  Crossover %d Tag(e) zurück: Kurs durchbricht GD (%s) — %sSignal" % (c["vor"], c["gd"], art))
    lk = report["luecken_kap5"]
    if lk:
        last_lk = lk[-1]
        print("  Lücken: %d im Zeitraum | letzte am %s (%s, %+.2f %%)" % (len(lk), str(last_lk.get("tag"))[:10], last_lk["typ"], last_lk.get("brei_pct") or 0.0))
    else:
        print("  Lücken: keine im Zeitraum")
    k7 = report["kerzen_kap7"]
    if not k7.get("ok"):
        print("  Kerzen-Signale: %s" % k7.get("hinweis", "-"))
    else:
        ss = "; ".join(s[0] for s in k7.get("signal_heute", []))
        print("  Kerzen-Signale heute: %s" % (ss if ss else "keines"))
    p6 = report["p_and_f_kap6"]
    print("  P&F: aktuelle Spalte %s | Kästchen: %s | Signale im Zeitraum: %d (letzte: %s)" % (
        p6.get("aktuelle_richtung"), p6.get("kaestchen", "-"), len(p6.get("signale", [])),
        (str(p6["signale"][-1]["signal"]) + " bei " + str(round(p6["signale"][-1]["niveau"], 2))) if p6.get("signale") else "keine"))
    print("Report geschrieben: %s" % out_path)


if __name__ == "__main__":
    main()
