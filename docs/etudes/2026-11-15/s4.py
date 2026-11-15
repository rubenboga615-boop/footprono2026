import csv, json, sys, numpy as np
from collections import defaultdict
from scipy.stats import nbinom, poisson
from scipy.optimize import brentq
csv.field_size_limit(10**9); D="/opt/fpdata/study/srv/"
res = {}
for r in csv.reader(open(D+"results.psv"), delimiter="|"):
    f = lambda x: float(x) if x != "" else np.nan
    res[int(r[0])] = dict(comp=r[1], hg=f(r[2]), ag=f(r[3]), hht=f(r[4]), aht=f(r[5]), corners=f(r[6])+f(r[7]), cards=f(r[8])+f(r[9]))
odds = defaultdict(dict)   # (match, bet, line-key) -> {book: {sel: price}}
def parse(bet, value):
    if bet in ("Match Winner","First Half Winner"): return ("", {"Home":"home","Draw":"draw","Away":"away"}.get(value))
    if bet == "Double Chance": return ("", {"Home/Draw":"1X","Home/Away":"12","Draw/Away":"X2"}.get(value))
    if bet == "Both Teams Score": return ("", value.lower())
    side, _, line = value.partition(" ")
    return (line, side.lower())
for mid, bk, bet, value, price in csv.reader(open(D+"odds.psv"), delimiter="|"):
    line, sel = parse(bet, value)
    if sel is None: continue
    odds[(int(mid), bet, line)].setdefault(bk, {})[sel] = float(price)
def settle(mid, bet, line, sel):
    """1 gagné, 0 perdu, None remboursé / inconnu."""
    r = res[mid]
    if bet in ("Match Winner","Double Chance"):
        h, a = r["hg"], r["ag"]
    elif bet == "First Half Winner":
        h, a = r["hht"], r["aht"]
    if bet in ("Match Winner","First Half Winner","Double Chance"):
        if np.isnan(h) or np.isnan(a): return None
        o = "home" if h > a else ("draw" if h == a else "away")
        if bet == "Double Chance": return int(o in {"1X":("home","draw"),"12":("home","away"),"X2":("draw","away")}[sel])
        return int(o == sel)
    if bet == "Both Teams Score": return int((r["hg"] > 0 and r["ag"] > 0) == (sel == "yes"))
    tot = {"Goals Over/Under": r["hg"]+r["ag"], "Goals Over/Under First Half": r["hht"]+r["aht"], "Corners Over Under": r["corners"], "Cards Over/Under": r["cards"]}[bet]
    if np.isnan(tot): return None
    L = float(line)
    if tot == L: return None
    return int((tot > L) == (sel == "over"))
NSEL = {"Match Winner":3,"First Half Winner":3,"Double Chance":3,"Both Teams Score":2}
print("== A. Marge moyenne du bookmaker par marché (cotes d'avant-match réelles du serveur)")
marg = defaultdict(list)
for (mid, bet, line), books in odds.items():
    for bk, sels in books.items():
        k = NSEL.get(bet, 2)
        if len(sels) != k: continue
        s = sum(1/p for p in sels.values())
        if bet == "Double Chance": s = s/2
        if bet.startswith("Goals Over/Under") and line not in ("1.5","2.5","3.5","0.5"): continue
        marg[(bet, bk)].append(s-1)
for bet in ("Match Winner","Double Chance","Both Teams Score","Goals Over/Under","First Half Winner","Goals Over/Under First Half","Corners Over Under","Cards Over/Under"):
    print(f"  {bet:30s}", "  ".join(f"{bk} {100*np.mean(marg[(bet,bk)]):5.1f} % (n={len(marg[(bet,bk)])})" for bk in ("Pinnacle","Bet365","1xBet") if marg[(bet,bk)]))

print("\n== B. Résultats réels par tranche de cote (tous marchés ci-dessus, hors lignes entières)")
rows = []  # (bet, book, price, win, best, pinn_p)
for (mid, bet, line), books in odds.items():
    k = NSEL.get(bet, 2)
    sels = set().union(*[set(s) for s in books.values()])
    pin = books.get("Pinnacle", {})
    pp = {}
    if len(pin) == k and bet != "Double Chance":
        inv = np.array([1/pin[s] for s in pin]); kk = brentq(lambda z: (inv**z).sum()-1, 0.3, 5)
        pp = dict(zip(pin, inv**kk))
    for sel in sels:
        w = settle(mid, bet, line, sel)
        if w is None: continue
        prices = {bk: s[sel] for bk, s in books.items() if sel in s}
        rows.append((bet, mid, line, sel, prices, w, pp.get(sel)))
def rep(label, sub, pricef):
    pr = np.array([pricef(r[4]) for r in sub], float); w = np.array([r[5] for r in sub]); ok = ~np.isnan(pr)
    pr, w = pr[ok], w[ok]
    if len(pr) < 30: print(f"  {label:44s} n={len(pr)}"); return
    ret = np.where(w == 1, pr-1, -1)
    print(f"  {label:44s} paris {len(pr):6d}  réussite {100*w.mean():5.1f} %  cote {pr.mean():.2f}  rendement {100*ret.mean():+6.2f} % ± {200*ret.std()/np.sqrt(len(pr)):.2f}")
g = lambda bk: (lambda p: p.get(bk, np.nan))
best = lambda p: max(p.values())
for lo, hi in ((1.0,1.3),(1.3,1.5),(1.5,1.7),(1.7,2.0),(2.0,3.0),(3.0,6.0),(6.0,100)):
    sub = [r for r in rows if "Bet365" in r[4] and lo <= r[4]["Bet365"] < hi]
    rep(f"Bet365 {lo}-{hi}", sub, g("Bet365")); rep("   → meilleure des 3", sub, best)
print("  par marché, cote Bet365 < 1,70 :")
for bet in ("Match Winner","Double Chance","Both Teams Score","Goals Over/Under","First Half Winner","Goals Over/Under First Half","Corners Over Under","Cards Over/Under"):
    sub = [r for r in rows if r[0]==bet and "Bet365" in r[4] and r[4]["Bet365"] < 1.7]
    rep(f"   {bet}", sub, g("Bet365")); rep(f"      → meilleure des 3", sub, best)
print("  quel bookmaker paie le mieux (sélections cotées par les 3) :")
c = defaultdict(int); tot = 0; gain = []
for r in rows:
    if len(r[4]) == 3:
        tot += 1; c[max(r[4], key=r[4].get)] += 1; gain.append(max(r[4].values())/r[4]["Bet365"]-1)
print("   ", {k: f"{100*v/tot:.0f} %" for k, v in c.items()}, f"; meilleure cote / Bet365 : +{100*np.mean(gain):.1f} % en moyenne (n={tot})")

print("\n== C. Moteur publié contre Pinnacle (marge retirée, puissance), matchs avec prévision avant le coup d'envoi")
preds = {int(r[0]): (json.loads(r[1]), json.loads(r[2])) for r in (l.rstrip("\n").split("\t") for l in open(D+"preds.tsv"))}
def nbpmf(mean, size, n=40):
    k = np.arange(n)
    return poisson.pmf(k, mean) if size >= 999 else nbinom.pmf(k, size, size/(size+mean))
def engine_p(mid, bet, line, sel):
    if mid not in preds: return None
    mk, cn = preds[mid]
    key = {"Match Winner": f"1X2||{sel}", "First Half Winner": f"HT_1X2||{sel}", "Both Teams Score": f"BTTS||{sel}",
           "Goals Over/Under": f"OU|{line}|{sel}", "Goals Over/Under First Half": f"HT_OU|{line}|{sel}"}.get(bet)
    if key: return mk[key][0] if key in mk else None
    stat = {"Corners Over Under":"corners","Cards Over/Under":"cards"}.get(bet)
    if stat and stat in cn:
        c = cn[stat]; tot = np.convolve(nbpmf(c["mean_home"], c["size"]), nbpmf(c["mean_away"], c["size"]))
        over = tot[np.arange(len(tot)) > float(line)].sum()
        return over if sel == "over" else 1-over
    return None
for bet in ("Match Winner","Goals Over/Under","Both Teams Score","First Half Winner","Goals Over/Under First Half","Corners Over Under","Cards Over/Under"):
    le, lm, agree, dis = [], [], [], []
    for r in rows:
        if r[0] != bet or r[6] is None: continue
        pe = engine_p(r[1], bet, r[2], r[3])
        if pe is None or not (0 < pe < 1): continue
        w = r[5]; pmk = r[6]
        le.append(-np.log(pe if w else 1-pe)); lm.append(-np.log(pmk if w else 1-pmk))
        price = max(r[4].values()); ret = price-1 if w else -1
        (agree if pe >= pmk + 0.03 else dis if pe <= pmk - 0.03 else []).append(ret)
    if len(le) < 50: print(f"  {bet:30s} n={len(le)} (trop peu)"); continue
    le, lm = np.array(le), np.array(lm); d = le-lm
    f = lambda x: f"{100*np.mean(x):+6.1f} % ± {200*np.std(x)/np.sqrt(len(x)):.1f} (n={len(x)})" if len(x) > 20 else f"n={len(x)}"
    print(f"  {bet:30s} n={len(le):5d}  moteur {le.mean():.4f}  Pinnacle {lm.mean():.4f}  écart {d.mean():+.4f} ± {2*d.std()/np.sqrt(len(d)):.4f}")
    print(f"       moteur au-dessus de la cote d'au moins 3 pts : {f(agree)} ; au-dessous : {f(dis)}")

print("\n== D. Prix payé par rapport à Pinnacle (probabilité Pinnacle, marge retirée) : pari à la meilleure cote Bet365/1xBet")
def repd(label, sub):
    pr = np.array([max(v for k, v in r[4].items() if k != "Pinnacle") for r in sub]); w = np.array([r[5] for r in sub])
    if len(pr) < 30: print(f"  {label:50s} n={len(pr)}"); return
    ret = np.where(w == 1, pr-1, -1)
    print(f"  {label:50s} paris {len(pr):6d}  réussite {100*w.mean():5.1f} %  cote {pr.mean():.2f}  rendement {100*ret.mean():+6.2f} % ± {200*ret.std()/np.sqrt(len(pr)):.2f}")
cand = [r for r in rows if r[6] is not None and any(k != "Pinnacle" for k in r[4])]
ev = lambda r: r[6]*max(v for k, v in r[4].items() if k != "Pinnacle")
for lo, hi in ((0, .90), (.90, .95), (.95, .98), (.98, 1.0), (1.0, 1.03), (1.03, 9)):
    repd(f"p Pinnacle × cote entre {lo:.2f} et {hi:.2f}", [r for r in cand if lo <= ev(r) < hi])
print("  idem, cotes de 1,25 à 2,00 seulement :")
for lo, hi in ((0, .95), (.95, 1.0), (1.0, 9)):
    repd(f"p Pinnacle × cote entre {lo:.2f} et {hi:.2f}", [r for r in cand if lo <= ev(r) < hi and 1.25 <= max(v for k, v in r[4].items() if k != "Pinnacle") < 2.0])
