import pickle, numpy as np
from scipy.optimize import minimize_scalar, brentq
d = pickle.load(open("/opt/fpdata/study/data.pkl", "rb"))
pred, odds = d["pred"], d["odds"]
n = len(pred.match_id); mid = np.array(pred.match_id); season = np.array(pred.season); comp = np.array(pred.competition)
y = np.array(pred.outcome_1x2); pm = np.array(pred.model_1x2)
def book(b, t, market="1X2", sels=("home","draw","away")):
    out = np.full((n, len(sels)), np.nan)
    for i, m in enumerate(mid):
        o = odds.get(int(m), {})
        for j, s in enumerate(sels): out[i, j] = o.get((b, market, t, s), np.nan)
    return out
B = {(b, t): book(b, t) for b in ("Avg","Max","B365","PS") for t in ("pre","close")}
def prop(o): inv = 1/o; return inv/inv.sum(1, keepdims=True)
def power(o, k=None):
    """Méthode puissance : p_i = (1/o_i)^k, k tel que somme = 1 (retire plus de marge aux outsiders)."""
    out = np.full(o.shape, np.nan)
    for i in range(len(o)):
        if np.isnan(o[i]).any(): continue
        inv = 1/o[i]
        kk = brentq(lambda k: (inv**k).sum() - 1, 0.5, 3)
        out[i] = inv**kk
    return out
def ll(p, yy): return -np.mean(np.log(np.clip(p[np.arange(len(yy)), yy], 1e-12, 1)))
win = np.zeros((n,3), bool); win[np.arange(n), y] = True
def report(label, m, price):
    k = m.sum()
    if k < 20: print(f"  {label:50s} {k} paris"); return
    ret = np.where(win[m], price[m]-1, -1.0)
    print(f"  {label:50s} paris {k:6d}  réussite {win[m].mean()*100:5.1f} %  cote {price[m].mean():.2f}  rendement {ret.mean()*100:+6.2f} % ± {200*ret.std()/np.sqrt(k):.2f}")
okA = ~np.isnan(B[("Avg","pre")]).any(1) & ~np.isnan(B[("Max","pre")]).any(1) & ~np.isnan(B[("B365","pre")]).any(1)
val, test = okA & (season<=2021), okA & (season>=2022)
avg, mx, b365, ps = B[("Avg","pre")], B[("Max","pre")], B[("B365","pre")], B[("PS","pre")]

print("== 1. Retirer la marge : proportionnel contre méthode puissance (log loss, cote moyenne d'avant-match)")
pp, pw = prop(avg), power(avg)
for nm, m in (("validation", val), ("test", test)):
    print(f"  {nm}: proportionnel {ll(pp[m], y[m]):.5f}   puissance {ll(pw[m], y[m]):.5f}")
dl = -np.log(pw[test][np.arange(test.sum()), y[test]]) + np.log(pp[test][np.arange(test.sum()), y[test]])
print(f"  puissance − proportionnel (test) : {dl.mean():+.5f} ± {2*dl.std()/np.sqrt(len(dl)):.5f}")
print("  calibration par tranche de probabilité (test) : annoncé proportionnel / puissance → observé")
for lo, hi in ((0,.1),(.1,.2),(.2,.3),(.3,.4),(.4,.5),(.5,.6),(.6,.7),(.7,.8),(.8,1)):
    m = np.repeat(test[:,None],3,1) & (pp>=lo) & (pp<hi)
    print(f"    {lo:.1f}-{hi:.1f} n={m.sum():6d}  {pp[m].mean():.3f} / {pw[m].mean():.3f} → {win[m].mean():.3f}")

print("\n== 2. Cotes courtes (B365 < 1,70) regroupées, par période et par saison")
short = (b365 < 1.7)
for nm, m in (("validation 2018-21", val), ("test 2022-26", test)):
    mm = np.repeat(m[:,None],3,1) & short
    report(f"{nm} chez B365", mm, b365); report(f"{nm} meilleure cote", mm, mx); report(f"{nm} cote moyenne", mm, avg)
for s in sorted(set(season[okA])):
    mm = np.repeat((okA & (season==s))[:,None],3,1) & short
    report(f"saison {s} meilleure cote", mm, mx)

print("\n== 3. Pinnacle (marge retirée, puissance) comme probabilité de référence ; pari chez B365 ou à la meilleure cote")
okP = okA & ~np.isnan(ps).any(1)
pP = power(np.where(np.isnan(ps), np.nan, ps))
for nm, m in (("validation", okP & (season<=2021)), ("test", okP & (season>=2022))):
    mm = np.repeat(m[:,None],3,1)
    print(f" {nm} ({m.sum()} matchs) ; log loss Pinnacle {ll(pP[m], y[m]):.4f}  moyenne {ll(pw[m], y[m]):.4f}")
    for thr in (0.0, 0.02, 0.04):
        report(f"p Pinnacle × B365 > {1+thr:.2f}", mm & (pP*b365 > 1+thr), b365)
    for thr in (0.0, 0.02, 0.04):
        report(f"p Pinnacle × meilleure cote > {1+thr:.2f} et cote < 3", mm & (pP*mx > 1+thr) & (mx<3), mx)
    for thr in (0.0, 0.02, 0.04):
        report(f"p Pinnacle × meilleure cote > {1+thr:.2f} et cote < 1,7", mm & (pP*mx > 1+thr) & (mx<1.7), mx)

print("\n== 4. Plus/moins 2,5 buts : même analyse")
ou = {(b,t): book(b,t,"OU",("over","under")) for b in ("Avg","Max","B365","PS") for t in ("pre",)}
yo = np.array(pred.outcome_ou25); wino = np.zeros((n,2),bool); wino[np.arange(n), 1-yo] = True
okO = ~np.isnan(ou[("Avg","pre")]).any(1) & ~np.isnan(ou[("Max","pre")]).any(1) & ~np.isnan(ou[("B365","pre")]).any(1)
pmo = np.array(pred.model_ou25); pmo2 = np.stack([pmo, 1-pmo], 1); pko = prop(ou[("Avg","pre")])
for nm, m in (("validation", okO & (season<=2021)), ("test", okO & (season>=2022))):
    yy = 1-yo[m]
    print(f"  {nm} ({m.sum()}): log loss moteur {ll(pmo2[m], yy):.4f}  cote {ll(pko[m], yy):.4f}")
def reporto(label, m, price):
    k = m.sum()
    if k < 20: print(f"  {label:50s} {k} paris"); return
    ret = np.where(wino[m], price[m]-1, -1.0)
    print(f"  {label:50s} paris {k:6d}  réussite {wino[m].mean()*100:5.1f} %  cote {price[m].mean():.2f}  rendement {ret.mean()*100:+6.2f} % ± {200*ret.std()/np.sqrt(k):.2f}")
tO = np.repeat((okO & (season>=2022))[:,None],2,1); bo, mo = ou[("B365","pre")], ou[("Max","pre")]
for lo, hi in ((1.0,1.5),(1.5,1.7),(1.7,2.0),(2.0,2.5),(2.5,5)):
    m = tO & (bo>=lo) & (bo<hi); reporto(f"B365 {lo}-{hi}", m, bo); reporto("   → meilleure cote", m, mo)
