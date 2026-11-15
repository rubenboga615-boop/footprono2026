import pickle, numpy as np
from scipy.optimize import minimize_scalar, brentq
d = pickle.load(open("/opt/fpdata/study/data_server.pkl", "rb"))
pred, odds = d["pred"], d["odds"]
n = len(pred.match_id); mid = np.array(pred.match_id); season = np.array(pred.season); comp = np.array(pred.competition)
y = np.array(pred.outcome_1x2); pm = np.array(pred.model_1x2)
def book(b, t, market="1X2", sels=("home","draw","away")):
    out = np.full((n, len(sels)), np.nan)
    for i, m in enumerate(mid):
        o = odds.get(int(m), {})
        for j, s in enumerate(sels): out[i, j] = o.get((b, market, t, s), np.nan)
    return out
def power(o):
    out = np.full(o.shape, np.nan)
    for i in range(len(o)):
        if np.isnan(o[i]).any(): continue
        inv = 1/o[i]; out[i] = inv**brentq(lambda k: (inv**k).sum()-1, 0.3, 4)
    return out
def ll(p, yy): return -np.mean(np.log(np.clip(p[np.arange(len(yy)), yy], 1e-12, 1)))
avg = book("Avg","pre"); mk = power(avg)
BIG = np.isin(comp, ["EPL","LA_LIGA","SERIE_A","BUNDESLIGA","LIGUE_1"])
ok = ~np.isnan(mk).any(1)
def blend(w, a, b):
    p = np.exp(w*np.log(a)+(1-w)*np.log(b)); return p/p.sum(1, keepdims=True)
for label, grp in (("5 grands championnats (moteur avec xG)", BIG), ("autres championnats (sans xG)", ~BIG)):
    val, test = ok & grp & (season<=2021), ok & grp & (season>=2022)
    w = minimize_scalar(lambda w: ll(blend(w, pm, mk)[val], y[val]), bounds=(0,1), method="bounded").x
    wt = minimize_scalar(lambda w: ll(blend(w, pm, mk)[test], y[test]), bounds=(0,1), method="bounded").x
    pb = blend(w, pm, mk)
    dl = -np.log(pb[test][np.arange(test.sum()), y[test]]) + np.log(mk[test][np.arange(test.sum()), y[test]])
    print(f"== 1X2 {label}: val {val.sum()}, test {test.sum()}")
    print(f"   poids du moteur appris sur validation {w:.3f} (optimum a posteriori sur test : {wt:.3f})")
    print(f"   test : moteur {ll(pm[test],y[test]):.4f}  cote {ll(mk[test],y[test]):.4f}  combiné {ll(pb[test],y[test]):.4f}  (combiné − cote {dl.mean():+.5f} ± {2*dl.std()/np.sqrt(len(dl)):.5f})")
# plus/moins 2,5
ou = book("Avg","pre","OU",("over","under")); mo = power(ou); yo = 1-np.array(pred.outcome_ou25)
po = np.array(pred.model_ou25); po2 = np.stack([po,1-po],1); oko = ~np.isnan(mo).any(1)
for label, grp in (("5 grands (xG)", BIG), ("autres", ~BIG)):
    val, test = oko & grp & (season<=2021), oko & grp & (season>=2022)
    w = minimize_scalar(lambda w: ll(blend(w, po2, mo)[val], yo[val]), bounds=(0,1), method="bounded").x
    pb = blend(w, po2, mo)
    dl = -np.log(pb[test][np.arange(test.sum()), yo[test]]) + np.log(mo[test][np.arange(test.sum()), yo[test]])
    print(f"== +/-2,5 {label}: poids moteur {w:.3f} ; test moteur {ll(po2[test],yo[test]):.4f} cote {ll(mo[test],yo[test]):.4f} combiné {ll(pb[test],yo[test]):.4f} ({dl.mean():+.5f} ± {2*dl.std()/np.sqrt(len(dl)):.5f})")
