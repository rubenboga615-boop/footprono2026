import pickle, numpy as np
from scipy.optimize import minimize_scalar
d = pickle.load(open("/opt/fpdata/study/data.pkl", "rb"))
pred, odds, hist = d["pred"], d["odds"], d["hist"]
n = len(pred.match_id)
mid = np.array(pred.match_id); season = np.array(pred.season); comp = np.array(pred.competition)
y = np.array(pred.outcome_1x2); pm = np.array(pred.model_1x2)
SEL = ("H", "D", "A")
def book(b, timing, market="1X2", sels=SEL):
    out = np.full((n, len(sels)), np.nan)
    for i, m in enumerate(mid):
        o = odds.get(int(m), {})
        for j, s in enumerate(sels):
            out[i, j] = o.get((b, market, timing, s), np.nan)
    return out
# noms des sélections
keys = set(k[3] for o in list(odds.values())[:2000] for k in o if k[1] == "1X2"); print("sel 1X2:", keys)
keys_ou = set(k[3] for o in list(odds.values())[:2000] for k in o if k[1] == "OU"); print("sel OU:", keys_ou)
SEL = tuple(sorted(keys, key=lambda s: {"H":0,"1":0,"home":0,"D":1,"X":1,"draw":1,"A":2,"2":2,"away":2}[s]))
B = {(b, t): book(b, t, sels=SEL) for b in ("Avg", "Max", "B365", "PS") for t in ("pre", "close")}
def implied(o):
    inv = 1 / o; return inv / inv.sum(1, keepdims=True)
def ll(p, yy): return -np.mean(np.log(np.clip(p[np.arange(len(yy)), yy], 1e-12, 1)))
ok = ~np.isnan(B[("Avg","pre")]).any(1) & ~np.isnan(B[("Max","pre")]).any(1) & ~np.isnan(B[("B365","pre")]).any(1)
okc = ok & ~np.isnan(B[("Avg","close")]).any(1)
val = ok & (season <= 2021); test = ok & (season >= 2022)
print("matchs val/test:", val.sum(), test.sum())
mk = implied(np.where(np.isnan(B[("Avg","pre")]), 2.0, B[("Avg","pre")]))
mkc = implied(np.where(np.isnan(B[("Avg","close")]), 2.0, B[("Avg","close")]))
def blend(w, a=pm, b=mk):
    p = np.exp(w * np.log(a) + (1 - w) * np.log(b)); return p / p.sum(1, keepdims=True)
w = minimize_scalar(lambda w: ll(blend(w)[val], y[val]), bounds=(0, 1), method="bounded").x
print(f"\n== A. Log loss 1X2 (test 2022-2026, {test.sum()} matchs) ; poids moteur appris sur validation = {w:.3f}")
for name, p in (("moteur", pm), ("cote avant-match (Avg)", mk), ("combiné", blend(w))):
    print(f"  {name:28s} val {ll(p[val], y[val]):.4f}   test {ll(p[test], y[test]):.4f}")
t2 = test & okc
print(f"  cote de clôture (Avg)        test {ll(mkc[t2], y[t2]):.4f} (sur {t2.sum()})")
# différence appariée combiné - marché
dl = -np.log(blend(w)[test][np.arange(test.sum()), y[test]]) + np.log(mk[test][np.arange(test.sum()), y[test]])
print(f"  combiné − cote : {dl.mean():+.5f} ± {2*dl.std()/np.sqrt(len(dl)):.5f} (2 erreurs types)")

def report(label, mask_sel, price, win):
    k = mask_sel.sum()
    if k == 0: print(f"  {label:44s} aucun pari"); return
    ret = np.where(win[mask_sel], price[mask_sel] - 1, -1.0)
    print(f"  {label:44s} paris {k:6d}  réussite {win[mask_sel].mean()*100:5.1f} %  cote moy. {price[mask_sel].mean():.2f}  rendement {ret.mean()*100:+6.2f} % ± {200*ret.std()/np.sqrt(k):.2f}")

win = np.zeros((n, 3), bool); win[np.arange(n), y] = True
tm = np.repeat(test[:, None], 3, 1)
b365, mx = B[("B365","pre")], B[("Max","pre")]
print("\n== B. Biais favori / outsider (test, toutes issues 1X2) : même pari chez B365 puis à la meilleure cote")
for lo, hi in ((1.0,1.3),(1.3,1.5),(1.5,1.7),(1.7,2.0),(2.0,2.5),(2.5,3.5),(3.5,5),(5,10),(10,100)):
    m = tm & (b365 >= lo) & (b365 < hi)
    report(f"B365 {lo}-{hi}", m, b365, win); report(f"   → meilleure cote", m, mx, win)

pb = blend(w)
print("\n== C. Montante palier (cote B365 1,50-1,70), test")
rng = tm & (b365 >= 1.5) & (b365 < 1.7)
report("toutes les sélections de la plage", rng, b365, win)
report("moteur d'accord (p moteur ≥ p cote)", rng & (pm >= mk), b365, win)
report("moteur en désaccord (p moteur < p cote)", rng & (pm < mk), b365, win)
for thr in (0.0, 0.02, 0.04):
    report(f"p moteur − p cote ≥ {thr:.2f}", rng & (pm - mk >= thr), b365, win)
report("idem, payé à la meilleure cote (accord)", rng & (pm >= mk), mx, win)

print("\n== D. « Value » avec la probabilité combinée, meilleure cote, test")
for thr in (0.0, 0.02, 0.05, 0.10):
    report(f"p combinée × meilleure cote > {1+thr:.2f}", tm & (pb * mx > 1 + thr), mx, win)
print("   idem avec le moteur seul :")
for thr in (0.0, 0.05, 0.10):
    report(f"p moteur × meilleure cote > {1+thr:.2f}", tm & (pm * mx > 1 + thr), mx, win)
print("   idem avec la cote moyenne seule (aucun moteur) :")
for thr in (0.0, 0.02, 0.05):
    report(f"p cote moy. × meilleure cote > {1+thr:.2f}", tm & (mk * mx > 1 + thr), mx, win)
