"""Génère docs/maquettes/12-nouveau-visage/index.html : nouveau visage de FootProba."""
import sys
from pathlib import Path

OUT = Path(sys.argv[1])

CSS = r"""
:root{--bg:#0A0F0D;--bg2:#0E1512;--card:#131C18;--card2:#1A2520;--line:#243029;--lime:#C4F23A;--ink:#0A0F0D;
--sky:#5BC8FF;--amber:#F4B740;--coral:#FF6B6B;--green:#3DDC84;--txt:#EEF4F0;--t2:#A6B5AE;--t3:#6F7F78;--violet:#8B6BFF}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#050806;color:var(--txt);font-family:Manrope,system-ui,sans-serif;padding:28px 16px 60px}
.num,.big,h1,.tt{font-family:'Space Grotesk',Manrope,sans-serif}
header.top{max-width:1500px;margin:0 auto 10px;text-align:center}
header.top h1{font-size:30px;letter-spacing:-.5px}
header.top p{color:var(--t2);max-width:900px;margin:8px auto 0;line-height:1.55;font-size:14.5px}
.toc{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin:18px auto 6px;max-width:1100px}
.toc a{color:var(--t2);text-decoration:none;font-size:13px;border:1px solid var(--line);border-radius:20px;padding:6px 12px}
section{max-width:1500px;margin:38px auto 0}
section>h2{font-size:15px;color:var(--lime);letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px}
section>p.lead{color:var(--t2);font-size:13.5px;margin-bottom:16px;max-width:900px;line-height:1.5}
.grid{display:flex;flex-wrap:wrap;gap:24px}
.scr{width:330px}.cap{font-size:13.5px;font-weight:800;margin-bottom:3px}.why{font-size:12px;color:var(--t2);line-height:1.45;margin-bottom:10px;min-height:50px}
.tag{font-size:10px;font-weight:800;padding:2px 7px;border-radius:6px;margin-left:5px;vertical-align:middle}
.tag.new{background:var(--lime);color:var(--ink)}.tag.re{background:var(--card2);color:var(--sky)}
.ph{width:330px;height:700px;background:var(--bg);border-radius:34px;border:1px solid var(--line);overflow:hidden;position:relative;display:flex;flex-direction:column}
.ph.wide{width:1000px;height:600px;border-radius:16px}
.sb{display:flex;justify-content:space-between;font-size:11px;color:var(--t2);padding:11px 22px 3px;font-weight:700}
.bd{padding:6px 14px 12px;flex:1;display:flex;flex-direction:column;gap:10px;overflow:hidden}
.hd{display:flex;align-items:center;gap:9px}.hd .ttl{font-size:19px;font-weight:800;flex:1}.back{font-size:20px;color:var(--t2)}
.logo{width:30px;height:30px;border-radius:9px;background:var(--lime);display:grid;place-items:center;flex:none}
.logo i{width:14px;height:14px;border-radius:50%;border:3px solid var(--ink);display:block;position:relative}
.wordmark{font-family:'Space Grotesk';font-weight:700;font-size:18px;letter-spacing:-.3px;flex:1}
.wordmark b{color:var(--lime)}
.bal{background:var(--card2);border-radius:20px;padding:5px 10px;font-size:12px;font-weight:800}.bal small{color:var(--t3);font-weight:600}
.bell{width:32px;height:32px;border-radius:50%;background:var(--card2);display:grid;place-items:center;font-size:14px;position:relative}
.bell .dot{position:absolute;top:6px;right:7px;width:7px;height:7px;border-radius:50%;background:var(--coral)}
.card{background:var(--card);border-radius:18px;padding:12px}
.card2{background:var(--card2);border-radius:14px;padding:10px}
.row{display:flex;align-items:center;gap:8px}.row>.pill,.row>.num,.row>span:not(.f1){flex:none}.col{display:flex;flex-direction:column;gap:4px}.f1{flex:1;min-width:0}
.t2{color:var(--t2)}.t3{color:var(--t3)}.xs{font-size:11px}.sm{font-size:12.5px}.b{font-weight:800}
.lime{color:var(--lime)}.sky{color:var(--sky)}.amber{color:var(--amber)}.coral{color:var(--coral)}.green{color:var(--green)}
.pill{display:inline-flex;align-items:center;gap:5px;border-radius:20px;padding:4px 9px;font-size:11.5px;font-weight:700;background:var(--card2);white-space:nowrap}
.pill.l{background:var(--lime);color:var(--ink)}.pill.s{background:#13324A;color:var(--sky)}.pill.a{background:#3A2C0E;color:var(--amber)}
.pill.c{background:#3A1717;color:var(--coral)}.pill.g{background:#123222;color:var(--green)}.pill.o{background:transparent;border:1px solid var(--line);color:var(--t2)}
.chips{display:flex;gap:6px;overflow:hidden}
.chip{border-radius:12px;padding:7px 11px;font-size:12px;font-weight:700;background:var(--card);color:var(--t2);white-space:nowrap}
.chip.on{background:var(--lime);color:var(--ink)}
.day{display:flex;flex-direction:column;align-items:center;border-radius:14px;padding:6px 0;width:46px;background:var(--card);font-size:10.5px;color:var(--t3);font-weight:700}
.day b{font-size:15px;color:var(--txt);font-family:'Space Grotesk'}.day.on{background:var(--lime);color:var(--ink)}.day.on b{color:var(--ink)}
.btn{background:var(--lime);color:var(--ink);border-radius:16px;height:50px;display:grid;place-items:center;font-weight:800;font-size:15px}
.btn.o{background:transparent;border:1.5px solid var(--line);color:var(--txt)}.btn.d{background:var(--card2);color:var(--txt)}.btn.sm{height:40px;font-size:13px;border-radius:12px}
.inp{background:var(--card);border-radius:14px;padding:13px 14px;font-size:13.5px;color:var(--t3);border:1px solid var(--line)}
.lbl{font-size:11.5px;font-weight:700;color:var(--t2);margin-bottom:-5px}
.av{width:26px;height:26px;border-radius:50%;display:grid;place-items:center;font-size:10px;font-weight:800;flex:none;color:#fff}
.mrow{background:var(--card);border-radius:16px;padding:10px 11px;display:flex;flex-direction:column;gap:8px}
.mrow .tm{font-family:'Space Grotesk';font-weight:700;font-size:13px;width:40px;text-align:center}
.mrow .tm small{display:block;font-size:9.5px;color:var(--t3);font-family:Manrope}
.mrow .teams{flex:1;display:flex;flex-direction:column;gap:5px;font-size:13px;font-weight:700}
.odds{display:flex;gap:6px}
.odd{flex:1;background:var(--card2);border-radius:12px;height:46px;display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:'Space Grotesk';font-weight:700;font-size:14px;position:relative}
.odd small{font-family:Manrope;font-size:9.5px;color:var(--t3);font-weight:700}
.odd.on{background:var(--lime);color:var(--ink)}.odd.on small{color:#2a3a10}
.odd .eng{position:absolute;top:4px;right:6px;font-size:9px;color:var(--sky);font-family:Manrope}
.odd.on .eng{color:#2a3a10}
.bar{height:7px;border-radius:5px;background:var(--card2);overflow:hidden;display:flex}
.bar i{display:block;height:100%}
.duel{display:grid;grid-template-columns:84px 1fr 40px;gap:6px;align-items:center;font-size:11.5px}
.duel .bar i{border-radius:5px}
.nav{display:flex;justify-content:space-around;align-items:flex-end;padding:8px 6px 14px;border-top:1px solid var(--line);background:var(--bg2);font-size:10px;color:var(--t3);font-weight:700}
.nav div{display:flex;flex-direction:column;align-items:center;gap:3px;width:56px}.nav .ic{font-size:17px;line-height:1}
.nav .on{color:var(--lime)}
.nav .mid{margin-top:-24px}.nav .mid .ic{width:52px;height:52px;border-radius:18px;background:var(--lime);color:var(--ink);display:grid;place-items:center;font-size:20px;box-shadow:0 6px 20px #c4f23a40;position:relative}
.nav .mid .ic em{position:absolute;top:-5px;right:-5px;background:var(--coral);color:#fff;font-style:normal;font-size:10px;border-radius:9px;padding:1px 6px}
.slip{margin:0 10px 6px;background:var(--lime);color:var(--ink);border-radius:16px;padding:10px 14px;display:flex;align-items:center;gap:10px;font-weight:800;font-size:13px}
.slip .n{background:var(--ink);color:var(--lime);border-radius:9px;padding:2px 8px;font-size:12px}
.seg{display:flex;background:var(--card);border-radius:14px;padding:4px;gap:4px}
.seg div{flex:1;text-align:center;padding:8px 0;border-radius:10px;font-size:12px;font-weight:700;color:var(--t2)}
.seg .on{background:var(--card2);color:var(--txt)}
.hero{background:radial-gradient(120% 100% at 50% 0%,#1E3324 0%,var(--card) 70%);border-radius:20px;padding:14px}
.score{font-family:'Space Grotesk';font-size:30px;font-weight:700;letter-spacing:2px}
.ring{width:96px;height:96px;border-radius:50%;display:grid;place-items:center}
.ring div{width:76px;height:76px;border-radius:50%;background:var(--card);display:grid;place-items:center;text-align:center}
.li{display:flex;align-items:center;gap:10px;padding:11px 2px;border-bottom:1px solid var(--line);font-size:13.5px}.li:last-child{border:0}
.li .ic{width:30px;height:30px;border-radius:10px;background:var(--card2);display:grid;place-items:center;font-size:14px}
.sw{width:38px;height:22px;border-radius:12px;background:var(--lime);position:relative;flex:none}.sw::after{content:"";position:absolute;right:3px;top:3px;width:16px;height:16px;border-radius:50%;background:var(--ink)}
.sw.off{background:var(--card2)}.sw.off::after{left:3px;right:auto;background:var(--t3)}
.step{display:flex;gap:10px;align-items:center}
.dot{width:26px;height:26px;border-radius:50%;display:grid;place-items:center;font-size:11px;font-weight:800;flex:none}
.dot.w{background:var(--green);color:var(--ink)}.dot.l{background:var(--coral);color:var(--ink)}.dot.c{background:var(--lime);color:var(--ink)}.dot.n{border:1.5px solid var(--line);color:var(--t3)}
.vline{width:2px;height:14px;background:var(--line);margin-left:12px}
.tbl{width:100%;border-collapse:collapse;font-size:12px}.tbl td,.tbl th{padding:6px 2px;text-align:right;border-bottom:1px solid var(--line)}
.tbl th{color:var(--t3);font-weight:700;font-size:10.5px}.tbl td:first-child,.tbl th:first-child{text-align:left}
.lock{position:absolute;inset:0;background:linear-gradient(180deg,#0a0f0d00 0%,#0a0f0dd9 35%,#0a0f0d 60%);display:flex;flex-direction:column;justify-content:flex-end;padding:18px 16px 22px;gap:10px}
.sheet{position:absolute;left:0;right:0;bottom:0;background:var(--card);border-radius:24px 24px 0 0;padding:10px 16px 20px;display:flex;flex-direction:column;gap:10px;box-shadow:0 -10px 30px #0008}
.grab{width:40px;height:4px;border-radius:3px;background:var(--line);margin:0 auto 4px}
.dim{position:absolute;inset:0;background:#000a}
.spark{display:flex;align-items:flex-end;gap:3px;height:46px}.spark i{flex:1;border-radius:3px 3px 0 0;background:var(--sky)}
.note{max-width:1100px;margin:40px auto 0;background:var(--card);border-radius:20px;padding:22px 24px;line-height:1.6;font-size:14px;color:var(--t2)}
.note h3{color:var(--txt);font-size:16px;margin:12px 0 6px}.note h3:first-child{margin-top:0}.note b{color:var(--txt)}.note li{margin-left:20px}
.pal{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}.pal div{width:120px;border-radius:12px;padding:44px 10px 8px;font-size:11px;font-weight:700}
"""

FONTS = '<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">'

TEAM_COLORS = ["#E2483D", "#2F6FE4", "#1E9E5A", "#F2A30F", "#8B6BFF", "#E04F9A", "#14A3B8", "#6B7A30", "#B55A26", "#4C5BD4"]


def av(name, i):
    return f'<span class="av" style="background:{TEAM_COLORS[i % 10]}">{name[:2].upper()}</span>'


def status():
    return '<div class="sb"><span>14:32</span><span>5G ▮▮▮ 82%</span></div>'


def topbar(title=None, back=False, right=""):
    if title is None:
        return ('<div class="hd"><div class="logo"><i></i></div><div class="wordmark">Foot<b>Proba</b></div>'
                '<span class="bal num">90 339 F <small>fictifs</small></span><div class="bell">🔔<span class="dot"></span></div></div>')
    return f'<div class="hd">{"<span class=back>←</span>" if back else ""}<div class="ttl">{title}</div>{right}</div>'


def nav(on="Matchs", count=2):
    items = [("⚽", "Matchs"), ("◎", "Direct"), ("mid", "Coupon"), ("↗", "Montante"), ("☺", "Moi")]
    out = []
    for ic, lab in items:
        if ic == "mid":
            out.append(f'<div class="mid {"on" if on == lab else ""}"><span class="ic">🎟<em>{count}</em></span>Coupon</div>')
        else:
            out.append(f'<div class="{"on" if on == lab else ""}"><span class="ic">{ic}</span>{lab}</div>')
    return '<div class="nav">' + "".join(out) + "</div>"


def slip(n=2, odds="3,42", gain="3 420"):
    return (f'<div class="slip"><span class="n">{n}</span><span class="f1">Mon coupon · cote <span class="num">{odds}</span></span>'
            f'<span class="num">→ {gain} F</span><span>⌃</span></div>')


def mrow(t, comp, h, a, o, e, sel=None, i=0, live=None, flag=""):
    tm = f'<div class="tm">{t}<small>{comp}</small></div>' if not live else f'<div class="tm coral">{live}<small>direct</small></div>'
    odds = ""
    for k, (lab, val, eng) in enumerate(zip(("1", "N", "2"), o, e)):
        on = " on" if sel == k else ""
        odds += f'<div class="odd{on}"><span class="eng">{eng}</span>{val}<small>{lab}</small></div>'
    return (f'<div class="mrow"><div class="row">{tm}<div class="teams"><div class="row">{av(h, i)}{h}</div>'
            f'<div class="row">{av(a, i + 3)}{a}</div></div>{flag}</div><div class="odds">{odds}</div></div>')


def duel(eng, cote, label="Le moteur", label2="Selon la cote"):
    return (f'<div class="duel"><span class="sky b">{label}</span><div class="bar"><i style="width:{eng}%;background:var(--sky)"></i></div><span class="num b sky">{eng} %</span></div>'
            f'<div class="duel"><span class="amber b">{label2}</span><div class="bar"><i style="width:{cote}%;background:var(--amber)"></i></div><span class="num b amber">{cote} %</span></div>')


def frame(num, title, why, body, tag="re", wide=False, extra=""):
    t = '<span class="tag new">Nouveau</span>' if tag == "new" else '<span class="tag re">Refait</span>'
    cls = "ph wide" if wide else "ph"
    w = ' style="width:1000px"' if wide else ""
    return (f'<div class="scr"{w}><p class="cap">{num}. {title}{t}</p><p class="why">{why}</p>'
            f'<div class="{cls}">{status() if not wide else ""}<div class="bd">{body}</div>{extra}</div></div>')


SECTIONS = []


def section(sid, name, lead, frames):
    SECTIONS.append((sid, name, lead, frames))


# ---------------------------------------------------------------- A. Démarrage
A = []
A.append(frame(1, "Bienvenue", "Le logo dès la première seconde (fini l'écran noir de 3 s), une promesse claire, et aucun bandeau avant l'inscription.",
 '<div style="flex:1;display:flex;flex-direction:column;justify-content:center;gap:18px">'
 '<div class="logo" style="width:64px;height:64px;border-radius:20px"><i style="width:28px;height:28px;border-width:5px"></i></div>'
 '<div class="big" style="font-size:32px;font-weight:700;line-height:1.1">Les vraies chances<br>de chaque match.</div>'
 '<div class="t2 sm" style="line-height:1.55">Un moteur qui calcule, une cote qu\'on compare, de l\'argent fictif pour s\'entraîner. Rien à payer pour commencer.</div>'
 '<div class="card">' + duel(62, 55) + '<div class="xs t3" style="margin-top:6px">Exemple : Athletic – Espanyol, moins de 2,5 buts</div></div></div>'
 '<div class="btn">Créer mon compte</div><div class="btn o">J\'ai déjà un compte</div>'
 '<div class="xs t3" style="text-align:center">Argent fictif · 18 ans et plus · jamais un conseil de pari</div>'))
A.append(frame(2, "Connexion", "Téléphone ou Google, sur un seul écran. Le pays est reconnu, l'indicatif est déjà rempli.",
 topbar("Connexion", True) +
 '<div class="t2 sm">Content de te revoir.</div>'
 '<div class="lbl">Téléphone</div><div class="row"><div class="inp" style="width:86px">🇨🇮 +225</div><div class="inp f1">07 00 00 00 00</div></div>'
 '<div class="lbl">Mot de passe</div><div class="inp">••••••••</div><div class="sm lime" style="text-align:right">Mot de passe oublié ?</div>'
 '<div class="btn">Se connecter</div><div class="row t3 xs"><div class="f1" style="height:1px;background:var(--line)"></div>ou<div class="f1" style="height:1px;background:var(--line)"></div></div>'
 '<div class="btn o">G&nbsp; Continuer avec Google</div><div style="flex:1"></div><div class="sm t2" style="text-align:center">Pas de compte ? <b class="lime">S\'inscrire</b></div>'))
A.append(frame(3, "Inscription", "Trois champs, puis le reste plus tard. L'âge et l'accord tiennent sur une seule case.",
 topbar("Créer mon compte", True) +
 '<div class="row"><span class="pill l">1 · Compte</span><span class="pill o">2 · Préférences</span></div>'
 '<div class="lbl">Prénom ou pseudo</div><div class="inp">Koffi</div>'
 '<div class="lbl">Téléphone</div><div class="row"><div class="inp" style="width:86px">🇨🇮 +225</div><div class="inp f1">07 00 00 00 00</div></div>'
 '<div class="lbl">Mot de passe</div><div class="inp">8 caractères au moins</div>'
 '<div class="card2 row sm"><span class="sw"></span><span class="t2">J\'ai 18 ans ou plus et j\'accepte les conditions. Argent fictif uniquement.</span></div>'
 '<div style="flex:1"></div><div class="btn">Continuer</div>'))
A.append(frame(4, "Presque prêt", "Le joueur choisit ses championnats et son style tout de suite : l'accueil est ensuite fait pour lui.",
 topbar("Presque prêt", True) +
 '<div class="row"><span class="pill o">1 · Compte</span><span class="pill l">2 · Préférences</span></div>'
 '<div class="b">Tes championnats</div><div style="display:flex;flex-wrap:wrap;gap:6px">'
 + "".join(f'<span class="chip{" on" if k in (0, 1, 3, 6) else ""}">{c}</span>' for k, c in enumerate(["Premier League", "Liga", "Serie A", "Ligue 1", "Bundesliga", "Ligue des champions", "CAN : éliminatoires", "Eredivisie", "Liga Portugal"])) +
 '</div><div class="b" style="margin-top:6px">Ta façon de jouer</div>'
 '<div class="card row"><span style="font-size:20px">🎯</span><div class="f1"><b class="sm">Paris simples</b><div class="xs t3">Un match, une sélection</div></div><span class="sw off"></span></div>'
 '<div class="card row" style="border:1.5px solid var(--lime)"><span style="font-size:20px">↗</span><div class="f1"><b class="sm">Montante</b><div class="xs t3">Des paliers qu\'on enchaîne</div></div><span class="sw"></span></div>'
 '<div style="flex:1"></div><div class="btn">C\'est parti</div>', tag="re"))
A.append(frame(5, "Mot de passe oublié", "Un code par SMS ou par WhatsApp, au choix ; le délai avant de redemander est affiché.",
 topbar("Mot de passe oublié", True) +
 '<div class="t2 sm">On t\'envoie un code à 6 chiffres.</div><div class="row"><div class="inp" style="width:86px">🇨🇮 +225</div><div class="inp f1">07 00 00 00 00</div></div>'
 '<div class="seg"><div class="on">SMS</div><div>WhatsApp</div></div>'
 '<div class="row" style="gap:6px;justify-content:center;margin-top:8px">' + "".join(f'<div class="inp num" style="width:40px;text-align:center;color:var(--txt);font-size:18px;padding:10px 0">{d}</div>' for d in "4821  ") +
 '</div><div class="xs t3" style="text-align:center">Renvoyer le code dans 0:42</div><div style="flex:1"></div><div class="btn">Valider</div>'))
section("demarrage", "A · Démarrage", "Premier contact : on montre la promesse avant de demander quoi que ce soit, et on ne montre plus trois messages avant le premier match.", A)

# ---------------------------------------------------------------- B. Matchs
B = []
days = '<div class="row" style="gap:6px">' + "".join(f'<div class="day{" on" if i == 1 else ""}">{d}<b>{n}</b></div>' for i, (d, n) in enumerate([("JEU", 19), ("VEN", 20), ("SAM", 21), ("DIM", 22), ("LUN", 23), ("MAR", 24)])) + "</div>"
B.append(frame(6, "Matchs (accueil)", "Nouvelle barre du bas : Coupon au centre, toujours à un pouce. Le coupon en cours reste visible en bas (ticket vert). Chaque cote montre la chance du moteur en petit.",
 topbar() + days +
 '<div class="chips"><span class="chip on">Mes championnats</span><span class="chip">Tous</span><span class="chip">Coupes</span><span class="chip">Sélections</span></div>'
 '<div class="row"><b class="sm f1">🇪🇸 Liga</b><span class="xs t3">chance du moteur en bleu</span></div>'
 + mrow("20:00", "J13", "Athletic Club", "Espanyol", ("1,62", "3,90", "5,60"), ("58%", "24%", "18%"), sel=None, i=0)
 + '<div class="row"><b class="sm f1">🇩🇪 2. Bundesliga</b></div>'
 + mrow("17:30", "J14", "Darmstadt", "Heidenheim", ("2,10", "3,40", "3,30"), ("44%", "27%", "29%"), sel=0, i=1)
 + mrow("17:30", "J14", "Hertha BSC", "Schalke 04", ("2,25", "3,30", "3,05"), ("41%", "28%", "31%"), i=2),
 extra=slip() + nav("Matchs")))
B.append(frame(7, "Matchs : filtres", "Les filtres sortent dans une feuille : championnats, marchés, « le moteur dépasse la cote ». Plus de rangée de dates écrasée.",
 topbar() + days + mrow("20:00", "J13", "Athletic Club", "Espanyol", ("1,62", "3,90", "5,60"), ("58%", "24%", "18%"), i=0),
 extra='<div class="dim"></div><div class="sheet"><div class="grab"></div><div class="row"><b class="f1" style="font-size:16px">Filtrer</b><span class="sm lime">Tout effacer</span></div>'
 '<div class="lbl">Championnats</div><div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:4px">' + "".join(f'<span class="chip{" on" if k < 3 else ""}">{c}</span>' for k, c in enumerate(["Liga", "Premier League", "2. Bundesliga", "Serie A", "Ligue 1", "Championship", "Eredivisie"])) + '</div>'
 '<div class="lbl">Afficher</div><div class="card2 row sm"><span class="f1">Seulement les matchs où le moteur dépasse la cote</span><span class="sw off"></span></div>'
 '<div class="card2 row sm"><span class="f1">Matchs pas encore commencés</span><span class="sw"></span></div><div class="btn">Voir 14 matchs</div></div>'))
B.append(frame(8, "Direct", "Onglet à part entière : les matchs en cours en grand, le score et la minute, mes paris liés au match signalés.",
 topbar("En direct", right='<span class="pill c">● 6 matchs</span>') +
 '<div class="hero"><div class="row xs t2"><span class="f1">🇪🇸 Liga</span><span class="coral b">67\'</span></div>'
 '<div class="row" style="margin:8px 0"><div class="f1 col" style="align-items:center">' + av("Athletic", 0) + '<b class="sm">Athletic</b></div><div class="score">1 – 0</div><div class="f1 col" style="align-items:center">' + av("Espanyol", 3) + '<b class="sm">Espanyol</b></div></div>'
 '<div class="row xs"><span class="pill g">✓ Ton pari : moins de 2,5 buts</span></div></div>'
 + mrow("", "", "Darmstadt", "Heidenheim", ("1,45", "4,20", "7,50"), ("71%", "20%", "9%"), i=1, live="54\'")
 + mrow("", "", "Hertha BSC", "Schalke 04", ("3,10", "2,90", "2,60"), ("30%", "36%", "34%"), i=2, live="MT"),
 extra=nav("Direct")))
B.append(frame(9, "Match : Probabilités", "En-tête « stade » avec l'heure et l'enjeu. Les marchés sont des cartes avec le duel Moteur / Cote, lisible en un coup d'œil.",
 topbar("", True, '<span class="f1"></span><span class="bell">☆</span><span class="bell">↗</span>') +
 '<div class="hero"><div class="row xs t2"><span class="f1">🇪🇸 Liga · J13</span><span>Ven. 20:00</span></div>'
 '<div class="row" style="margin:8px 0"><div class="f1 col" style="align-items:center">' + av("Athletic", 0) + '<b class="sm">Athletic</b><span class="xs t3">4e</span></div><div class="score" style="font-size:22px">20:00</div><div class="f1 col" style="align-items:center">' + av("Espanyol", 3) + '<b class="sm">Espanyol</b><span class="xs t3">15e</span></div></div></div>'
 '<div class="seg"><div class="on">Probabilités</div><div>Cotes</div><div>Analyse</div></div>'
 '<div class="card col" style="gap:7px"><div class="row"><b class="sm f1">Moins de 2,5 buts</b><span class="pill s">moteur au-dessus</span></div>' + duel(59, 50) + '<div class="row"><span class="xs t3 f1">1xBet · mise à jour 14:10</span><span class="odd" style="flex:none;width:76px;height:38px">2,02</span></div></div>'
 '<div class="card col" style="gap:7px"><div class="row"><b class="sm f1">Athletic gagne</b><span class="pill a">sous la cote</span></div>' + duel(58, 62) + '</div>'
 '<div class="card row sm"><span class="f1 t2">🔒 Handicaps, corners, cartons, mi-temps</span><span class="pill l">Premium</span></div>', extra=slip(1, "2,02", "2 020")))
B.append(frame(10, "Match : Cotes", "Toutes les cotes en grille de boutons de 46 px (avant 35 px). L'historique d'une cote s'ouvre d'un appui long.",
 topbar("Athletic – Espanyol", True) + '<div class="seg"><div>Probabilités</div><div class="on">Cotes</div><div>Analyse</div></div>'
 '<div class="chips"><span class="chip on">Principaux</span><span class="chip">Buts</span><span class="chip">Mi-temps</span><span class="chip">Handicaps</span></div>'
 '<div class="card col" style="gap:8px"><b class="sm">Résultat du match</b><div class="odds"><div class="odd"><span class="eng">58%</span>1,62<small>Athletic</small></div><div class="odd"><span class="eng">24%</span>3,90<small>Nul</small></div><div class="odd"><span class="eng">18%</span>5,60<small>Espanyol</small></div></div></div>'
 '<div class="card col" style="gap:8px"><b class="sm">Plus / moins de 2,5 buts</b><div class="odds"><div class="odd"><span class="eng">41%</span>1,78<small>Plus</small></div><div class="odd on"><span class="eng">59%</span>2,02<small>Moins</small></div></div><div class="xs t3">▼ 2,08 → 2,02 depuis l\'ouverture · appui long : historique</div></div>'
 '<div class="card col" style="gap:8px"><b class="sm">Les deux marquent</b><div class="odds"><div class="odd"><span class="eng">46%</span>1,95<small>Oui</small></div><div class="odd"><span class="eng">54%</span>1,80<small>Non</small></div></div></div>', extra=slip(1, "2,02", "2 020")))
B.append(frame(11, "Match : Analyse", "Forme, buts attendus et enjeu en visuels. Les cartes vides sont cachées (« Moyennes attendues » vide aujourd'hui) ; « matchs officiels » pour les sélections.",
 topbar("Athletic – Espanyol", True) + '<div class="seg"><div>Probabilités</div><div>Cotes</div><div class="on">Analyse</div></div>'
 '<div class="card"><b class="sm">Forme (5 derniers)</b><div class="row" style="margin-top:8px"><span class="sm f1">Athletic</span>' + "".join(f'<span class="dot {c}" style="width:22px;height:22px;font-size:10px">{t}</span>' for c, t in zip("wwnwl", "VVNVD")).replace("dot n", "dot n") + '</div><div class="row" style="margin-top:6px"><span class="sm f1">Espanyol</span>' + "".join(f'<span class="dot {c}" style="width:22px;height:22px;font-size:10px">{t}</span>' for c, t in zip("lnlwl", "DNDVD")) + '</div></div>'
 '<div class="card"><b class="sm">Buts attendus</b><div class="row" style="margin-top:8px"><span class="big num" style="font-size:26px">1,44</span><div class="f1 bar" style="height:10px"><i style="width:62%;background:var(--sky)"></i><i style="width:38%;background:var(--violet)"></i></div><span class="big num" style="font-size:26px">0,88</span></div><div class="row xs t3"><span class="f1">Athletic</span><span>Espanyol</span></div></div>'
 '<div class="card"><b class="sm">Enjeu</b><div class="sm t2" style="margin-top:6px;line-height:1.5">Athletic : à 2 points de la 4e place.<br>Espanyol : à 3 points de la zone de relégation.</div></div>'
 '<div class="card row sm"><span>🧑‍⚖️</span><span class="f1">Arbitre : J. Sánchez · 4,9 cartons / match</span><span class="t3">›</span></div>'))
B.append(frame(12, "Historique d'une cote", "Feuille courte avec une courbe, au lieu d'une liste de chiffres.",
 topbar("Athletic – Espanyol", True) + '<div class="card" style="height:300px"></div>',
 extra='<div class="dim"></div><div class="sheet"><div class="grab"></div><b>Moins de 2,5 buts · 1xBet</b>'
 '<div class="row"><span class="big num" style="font-size:28px">2,02</span><span class="pill c">▼ −0,06</span><span class="f1"></span><span class="xs t3">3 changements</span></div>'
 '<svg viewBox="0 0 300 90" style="width:100%;height:90px"><polyline fill="none" stroke="#5BC8FF" stroke-width="3" points="0,20 70,22 120,40 190,44 240,60 300,62"/><line x1="0" y1="89" x2="300" y2="89" stroke="#243029"/></svg>'
 '<div class="row xs t3"><span class="f1">Lun. 09:12 · 2,08</span><span>Ven. 14:10 · 2,02</span></div></div>'))
B.append(frame(13, "Équipe", "Fiche d'équipe : prochain match, forme, et le bouton « Suivre » (nouveau, voir les idées).",
 topbar("", True) + '<div class="hero col" style="align-items:center;gap:6px">' + av("Athletic", 0).replace("26px", "56px") + '<b style="font-size:18px">Athletic Club</b><span class="xs t3">Liga · 4e · 23 pts</span><span class="pill l">☆ Suivre</span></div>'
 '<div class="card row"><div class="f1"><div class="xs t3">Prochain match</div><b class="sm">vs Espanyol · ven. 20:00</b></div><span class="t3">›</span></div>'
 '<div class="card"><b class="sm">Cette saison</b><table class="tbl" style="margin-top:6px"><tr><th></th><th>Dom.</th><th>Ext.</th></tr><tr><td>Buts marqués</td><td>1,7</td><td>1,1</td></tr><tr><td>Buts encaissés</td><td>0,8</td><td>1,3</td></tr><tr><td>Corners</td><td>6,1</td><td>4,4</td></tr></table></div>'))
B.append(frame(14, "Arbitre et classement des arbitres", "Profil de l'arbitre en chiffres clés, puis le tableau du championnat trié par cartons.",
 topbar("Arbitres · Liga", True) + '<div class="card row"><div class="av" style="width:44px;height:44px;background:#2F6FE4;font-size:14px">JS</div><div class="f1"><b>J. Sánchez Martínez</b><div class="xs t3">11 matchs cette saison</div></div></div>'
 '<div class="row" style="gap:8px">' + "".join(f'<div class="card f1 col" style="align-items:center"><span class="big num" style="font-size:22px">{v}</span><span class="xs t3">{l}</span></div>' for v, l in [("4,9", "cartons"), ("0,3", "rouges"), ("28%", "pénaltys")]) + '</div>'
 '<div class="card"><table class="tbl"><tr><th>Arbitre</th><th>Matchs</th><th>Cartons</th></tr>' + "".join(f'<tr><td>{n}</td><td>{m}</td><td class="b">{c}</td></tr>' for n, m, c in [("Sánchez", 11, "4,9"), ("Hernández", 12, "4,6"), ("Munuera", 10, "4,2"), ("Gil", 11, "3,8"), ("Cuadra", 9, "3,5")]) + '</table></div>'))
B.append(frame(15, "Classement mérité", "Le vrai classement face au classement « mérité » d'après les occasions : les flèches disent qui est chanceux.",
 topbar("Classement mérité · Liga", True) + '<div class="seg"><div class="on">Mérité</div><div>Réel</div></div>'
 '<div class="card"><table class="tbl"><tr><th>#</th><th style="text-align:left">Équipe</th><th>Réel</th><th>Écart</th></tr>' + "".join(f'<tr><td>{i}</td><td style="text-align:left">{n}</td><td>{r}</td><td class="{c}">{d}</td></tr>' for i, n, r, c, d in [(1, "Barcelona", 1, "t3", "="), (2, "Real Madrid", 2, "t3", "="), (3, "Athletic", 4, "green", "▲1"), (4, "Atlético", 3, "coral", "▼1"), (5, "Villarreal", 7, "green", "▲2"), (6, "Betis", 5, "coral", "▼1")]) + '</table></div>'
 '<div class="xs t3">▲ : mérite mieux que son classement réel.</div>'))
section("matchs", "B · Matchs", "Le cœur de l'appli. Nouvelle barre du bas (Matchs · Direct · Coupon · Montante · Moi), coupon en ticket permanent, chance du moteur sur chaque cote.", B)

# ---------------------------------------------------------------- C. Coupons
C = []
C.append(frame(16, "Mon coupon (ticket)", "Le coupon s'ouvre par le bas depuis n'importe quel écran. Chaque sélection garde son duel Moteur / Cote ; mise rapide en un appui.",
 topbar() + '<div class="card" style="height:150px"></div>',
 extra='<div class="dim"></div><div class="sheet" style="top:90px"><div class="grab"></div><div class="row"><b class="f1" style="font-size:17px">Mon coupon</b><span class="pill o">Combiné · 2</span><span class="sm t3">Vider</span></div>'
 '<div class="card2 col" style="gap:6px"><div class="row"><b class="sm f1">Athletic – Espanyol</b><span class="t3">✕</span></div><div class="row xs"><span class="f1 t2">Moins de 2,5 buts</span><span class="num b" style="font-size:14px">2,02</span></div><div class="row xs"><span class="sky b">moteur 59 %</span><span class="amber b">cote 50 %</span></div></div>'
 '<div class="card2 col" style="gap:6px"><div class="row"><b class="sm f1">Darmstadt – Heidenheim</b><span class="t3">✕</span></div><div class="row xs"><span class="f1 t2">Darmstadt ou nul</span><span class="num b" style="font-size:14px">1,76</span></div><div class="row xs"><span class="sky b">moteur 66 %</span><span class="amber b">cote 57 %</span></div></div>'
 '<div class="row"><span class="t2 sm f1">Cote totale</span><b class="num" style="font-size:18px">3,56</b></div>'
 '<div class="row" style="gap:6px">' + "".join(f'<span class="chip{" on" if v == "1 000" else ""}" style="flex:1;text-align:center">{v}</span>' for v in ["500", "1 000", "2 000", "5 000"]) + '</div>'
 '<div class="row"><span class="t2 sm f1">Gain possible</span><b class="num lime" style="font-size:20px">3 560 F</b></div><div class="btn">Placer le pari · 1 000 F</div></div>'))
C.append(frame(17, "Pari placé", "Confirmation courte et claire, avec ce qui arrive ensuite (direct, notification au coup de sifflet final).",
 '<div style="flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:14px;text-align:center">'
 '<div style="width:80px;height:80px;border-radius:50%;background:var(--lime);display:grid;place-items:center;font-size:38px;color:var(--ink)">✓</div>'
 '<b style="font-size:22px">Pari n° 112 placé</b><div class="t2 sm">1 000 F fictifs · cote 3,56 · gain possible 3 560 F</div>'
 '<div class="card" style="width:100%;text-align:left"><div class="sm t2">Tu suivras tes matchs dans <b class="lime">Direct</b>. On te prévient au résultat (jamais entre 23 h et 8 h).</div></div></div>'
 '<div class="btn">Voir mes paris</div><div class="btn o">Retour aux matchs</div>', tag="re"))
C.append(frame(18, "Coupons (hub)", "Un seul endroit pour tous les coupons : le mien, le Coupon intelligent, les Coupons du jour, le coupon en direct.",
 topbar("Coupons") +
 '<div class="card row" style="border:1.5px solid var(--lime)"><span style="font-size:22px">🎟</span><div class="f1"><b>Mon coupon</b><div class="xs t3">2 sélections · cote 3,56</div></div><span class="pill l">Ouvrir</span></div>'
 '<div class="card col" style="gap:8px"><div class="row"><span style="font-size:22px">✨</span><div class="f1"><b>Coupon intelligent</b><div class="xs t3">Composé selon ton profil</div></div><span class="pill l">Premium</span></div><div class="row" style="gap:6px"><span class="chip">Sûr</span><span class="chip">Équilibré</span><span class="chip">Audacieux</span><span class="chip">Grosse cote</span></div></div>'
 '<div class="card col" style="gap:8px"><div class="row"><span style="font-size:22px">☀️</span><div class="f1"><b>Coupons du jour</b><div class="xs t3">3 coupons · mis à jour à 9 h</div></div><span class="t3">›</span></div><div class="row xs"><span class="pill a">2 sous la cote</span><span class="pill s">1 au-dessus</span></div></div>'
 '<div class="card row"><span style="font-size:22px">⚡</span><div class="f1"><b>Coupon en direct</b><div class="xs t3">Pendant les matchs en cours</div></div><span class="pill c">● 6</span></div>'
 '<div class="card row"><span style="font-size:22px">🕘</span><div class="f1"><b>Historique</b><div class="xs t3">Coupons déjà composés</div></div><span class="t3">›</span></div>', extra=nav("Coupon", 2)))
C.append(frame(19, "Coupon intelligent : réglages", "Le profil en grandes cartes, puis la période et la cote visée ; le reste dans « Plus de réglages ».",
 topbar("Coupon intelligent", True) + '<div class="row" style="gap:8px">' + "".join(f'<div class="card f1 col" style="gap:3px;{"border:1.5px solid var(--lime)" if k == 1 else ""}"><b class="sm">{n}</b><span class="xs t3">{d}</span></div>' for k, (n, d) in enumerate([("Sûr", "75–92 %"), ("Équilibré", "≈ 75 %")])) + '</div>'
 '<div class="row" style="gap:8px">' + "".join(f'<div class="card f1 col" style="gap:3px"><b class="sm">{n}</b><span class="xs t3">{d}</span></div>' for n, d in [("Audacieux", "≈ 60 %"), ("Grosse cote", "cote visée")]) + '</div>'
 '<div class="lbl">Période</div><div class="seg"><div class="on">Aujourd\'hui</div><div>48 h</div><div>3 jours</div></div>'
 '<div class="lbl">Sélections</div><div class="row" style="gap:6px">' + "".join(f'<span class="chip{" on" if n == "3" else ""}" style="flex:1;text-align:center">{n}</span>' for n in "23456") + '</div>'
 '<div class="card2 row sm"><span class="f1">Écarter les matchs déjà dans mes paris</span><span class="sw"></span></div><div class="sm lime">Plus de réglages ›</div><div style="flex:1"></div><div class="btn">Composer</div>'))
C.append(frame(20, "Coupon intelligent : résultat", "Le duel Moteur / Cote en tête du coupon, avec l'encadré ambre quand le moteur est sous la cote (proposition P1 du designer), et une pastille par sélection.",
 topbar("Équilibré · 3 sélections", True) +
 '<div class="card col" style="gap:7px"><div class="row"><b class="f1">Chance du coupon</b><span class="num b" style="font-size:18px">cote 2,30</span></div>' + duel(41, 43) +
 '<div class="card2 sm" style="background:#2E240C;color:#F7D58A;line-height:1.45">Le moteur est un peu sous la cote sur ce coupon : il le juge moins probable que le bookmaker.</div></div>'
 + "".join(f'<div class="card2 col" style="gap:4px"><div class="row"><b class="sm f1">{m}</b><span class="num b">{o}</span></div><div class="row xs"><span class="t2 f1">{s}</span><span class="pill {p}">{t}</span></div></div>' for m, s, o, p, t in [("Molde – Bodø/Glimt", "Bodø/Glimt ou nul", "1,22", "s", "moteur 86 % · cote 82 %"), ("Feyenoord – PSV", "Plus de 1,5 buts", "1,25", "a", "moteur 76 % · cote 80 %"), ("Lens – Lyon", "Moins de 4,5 buts", "1,10", "a", "moteur 84 % · cote 91 %")]) +
 '<div class="row xs t3"><span class="f1">Composé à 14:32</span><span>↻ Recomposer</span></div><div class="row" style="gap:8px"><div class="btn o f1">Partager</div><div class="btn f1">Ajouter au coupon</div></div>'))
C.append(frame(21, "Coupons du jour", "Trois cartes par profil, chacune avec sa pastille au-dessus / sous la cote (proposition P2) ; moteur 2 dans un onglet quand la comparaison est activée.",
 topbar("Coupons du jour", True) + '<div class="seg"><div class="on">Moteur 1</div><div>Moteur 2</div></div>'
 + "".join(f'<div class="card col" style="gap:7px"><div class="row"><b class="f1">{n}</b><span class="num b">cote {o}</span></div>' + duel(e, c) + f'<div class="row xs"><span class="t3 f1">{s} sélections · Premium : sélections et code 1xBet</span><span class="pill {p}">{t}</span></div></div>' for n, o, e, c, s, p, t in [("Sûr", "1,56", 64, 64, 3, "o", "à égalité"), ("Équilibré", "2,30", 41, 43, 3, "a", "sous la cote"), ("Audacieux", "4,60", 24, 21, 4, "s", "au-dessus")])))
C.append(frame(22, "Coupon du jour : détail", "Les sélections avec leur résultat en direct une fois les matchs commencés, et le code 1xBet à copier (Premium).",
 topbar("Audacieux · cote 4,60", True) +
 "".join(f'<div class="card2 row"><span class="dot {d}">{t}</span><div class="f1"><b class="sm">{m}</b><div class="xs t2">{s}</div></div><span class="num b">{o}</span></div>' for d, t, m, s, o in [("w", "✓", "Darmstadt – Heidenheim", "Darmstadt ou nul", "1,76"), ("c", "67'", "Athletic – Espanyol", "Moins de 2,5 buts", "2,02"), ("n", "21h", "Lens – Lyon", "Les deux marquent", "1,72"), ("n", "21h", "Inter – Roma", "Inter gagne", "1,95")]) +
 '<div class="card row"><div class="f1"><div class="xs t3">Code 1xBet</div><b class="num" style="font-size:18px;letter-spacing:2px">KX4F 9P2</b></div><span class="pill l">Copier</span></div><div class="btn">Ajouter à mon coupon</div>'))
C.append(frame(23, "Coupon en direct", "Les propositions pendant les matchs, avec la minute et le score ; la chance bouge en direct (flèche).",
 topbar("Coupon en direct", True, '<span class="pill c">● direct</span>') +
 "".join(f'<div class="card col" style="gap:6px"><div class="row xs"><span class="coral b">{mi}</span><span class="f1 t2">{m}</span><b class="num">{sc}</b></div><div class="row"><b class="sm f1">{s}</b><span class="odd" style="flex:none;width:70px;height:40px">{o}</span></div><div class="row xs"><span class="sky b">moteur {e} % {arrow}</span><span class="amber b" style="margin-left:8px">cote {c} %</span></div></div>' for mi, m, sc, s, o, e, c, arrow in [("67'", "Athletic – Espanyol", "1–0", "Moins de 2,5 buts", "1,48", 74, 68, "▲"), ("54'", "Darmstadt – Heidenheim", "2–1", "Plus de 3,5 buts", "2,40", 38, 42, "▼"), ("MT", "Hertha – Schalke", "0–0", "Moins de 1,5 buts", "2,10", 51, 48, "▲")]) +
 '<div class="xs t3">Cotes du direct : elles changent vite, le pari est refusé si la cote baisse.</div>'))
C.append(frame(24, "Partager un coupon", "Une image propre, prête pour WhatsApp et le statut, avec le logo et la mention « argent fictif ».",
 topbar("Partager", True) +
 '<div style="background:linear-gradient(160deg,#1E3324,#0E1512);border-radius:22px;padding:16px;border:1px solid var(--line)" class="col">'
 '<div class="row"><div class="logo"><i></i></div><div class="wordmark">Foot<b>Proba</b></div><span class="pill l">Cote 3,56</span></div>'
 + "".join(f'<div class="row sm" style="margin-top:8px"><span class="f1">{m}<div class="xs t3">{s}</div></span><b class="num">{o}</b></div>' for m, s, o in [("Athletic – Espanyol", "Moins de 2,5 buts", "2,02"), ("Darmstadt – Heidenheim", "Darmstadt ou nul", "1,76")]) +
 '<div class="xs t3" style="margin-top:10px">Pronostics en argent fictif · footproba.app</div></div>'
 '<div class="row" style="gap:8px;margin-top:6px">' + "".join(f'<div class="card f1 col" style="align-items:center;gap:4px"><span style="font-size:22px">{i}</span><span class="xs">{l}</span></div>' for i, l in [("💬", "WhatsApp"), ("◐", "Statut"), ("⤓", "Image"), ("🔗", "Lien")]) + '</div>'))
section("coupons", "C · Coupons", "Le coupon devient un ticket qu'on ouvre par le bas depuis partout ; l'onglet du centre regroupe tous les coupons.", C)

# ---------------------------------------------------------------- D. Montante
D = []
D.append(frame(25, "Mes montantes", "Chaque montante en carte avec ses paliers en pastilles : on voit tout de suite où on en est.",
 topbar("Montante") +
 '<div class="card col" style="gap:8px;border:1.5px solid var(--lime)"><div class="row"><b class="f1">Montante n° 9</b><span class="pill l">Palier 3 / 6</span></div>'
 '<div class="row" style="gap:5px">' + "".join(f'<span class="dot {c}" style="width:30px;height:30px">{t}</span>' for c, t in [("w", "1"), ("w", "2"), ("c", "3"), ("n", "4"), ("n", "5"), ("n", "6")]) + '</div>'
 '<div class="row sm"><span class="t2 f1">Mise en jeu</span><b class="num">3 240 F</b></div><div class="row sm"><span class="t2 f1">Objectif</span><b class="num lime">33 500 F</b></div><div class="btn sm">Jouer le palier 3</div></div>'
 '<div class="card col" style="gap:6px"><div class="row"><b class="f1">Montante n° 8</b><span class="pill c">Perdue au palier 2</span></div><div class="row" style="gap:5px">' + "".join(f'<span class="dot {c}" style="width:24px;height:24px">{t}</span>' for c, t in [("w", "1"), ("l", "2")]) + '</div></div>'
 '<div class="card col" style="gap:6px"><div class="row"><b class="f1">Montante n° 7</b><span class="pill g">Réussie · +11 200 F</span></div></div>'
 '<div class="btn o">+ Nouvelle montante</div>', extra=nav("Montante")))
D.append(frame(26, "Nouvelle montante", "Un simulateur en direct : la mise de départ et le nombre de paliers dessinent la courbe de gain.",
 topbar("Nouvelle montante", True) + '<div class="lbl">Mise de départ</div><div class="inp num" style="color:var(--txt);font-size:20px">2 000 F</div>'
 '<div class="lbl">Paliers</div><div class="row" style="gap:6px">' + "".join(f'<span class="chip{" on" if n == "6" else ""}" style="flex:1;text-align:center">{n}</span>' for n in "345678") + '</div>'
 '<div class="lbl">Cote par palier</div><div class="seg"><div>1,30–1,50</div><div class="on">1,50–1,70</div><div>1,70–1,90</div></div>'
 '<div class="card"><div class="row xs t3"><span class="f1">Si tout passe</span><span>Chance que tout passe (moteur)</span></div><div class="row"><b class="num lime f1" style="font-size:22px">33 500 F</b><b class="num sky" style="font-size:18px">≈ 5 %</b></div>'
 '<div class="spark" style="margin-top:8px">' + "".join(f'<i style="height:{h}%"></i>' for h in [12, 18, 28, 42, 64, 100]) + '</div></div><div style="flex:1"></div><div class="btn">Lancer la montante</div>'))
D.append(frame(27, "Montante : détail", "Les paliers en frise verticale, comme un parcours ; le palier en cours est mis en avant.",
 topbar("Montante n° 9", True) +
 '<div class="row" style="gap:8px">' + "".join(f'<div class="card f1 col" style="align-items:center"><span class="num b" style="font-size:16px">{v}</span><span class="xs t3">{l}</span></div>' for v, l in [("3 240", "en jeu"), ("2 / 6", "réussis"), ("33 500", "objectif")]) + '</div>'
 + "".join(
  (f'<div class="step"><span class="dot {d}">{n}</span><div class="f1 card2"><div class="row"><b class="sm f1">{m}</b><span class="num b">{o}</span></div><div class="xs t2">{s}</div></div></div>' + ('<div class="vline"></div>' if k < 3 else ""))
  for k, (d, n, m, s, o) in enumerate([("w", "1", "Barcelona – Getafe", "Barcelona gagne · 2 000 → 3 240", "1,62"), ("w", "2", "Inter – Torino", "Plus de 1,5 buts", "1,25"), ("c", "3", "À choisir", "Cote visée 1,50 à 1,70", "—"), ("n", "4", "", "", "")])) +
 '<div class="btn">Choisir le palier 3</div>'))
D.append(frame(28, "Palier : suggestions", "Les suggestions du moteur pour le palier (Premium), avec le duel Moteur / Cote ; moteur 1 et 2 côte à côte si la comparaison est activée.",
 topbar("Palier 3 · cote 1,50–1,70", True) +
 "".join(f'<div class="card col" style="gap:7px"><div class="row"><b class="sm f1">{m}</b><span class="num b">{o}</span></div><div class="xs t2">{s}</div>' + duel(e, c) + '</div>' for m, s, o, e, c in [("Lens – Lyon", "Lens ou nul", "1,58", 70, 63), ("Feyenoord – PSV", "Plus de 2,5 buts", "1,62", 64, 62), ("Porto – Braga", "Porto gagne", "1,55", 61, 65)]) +
 '<div class="xs t3">Classées par chance du moteur. Rien n\'est un conseil de pari.</div>'))
D.append(frame(29, "Montante : analyse", "Mes chiffres de montante : taux de réussite par palier, où je perds le plus souvent.",
 topbar("Mes montantes · analyse", True) +
 '<div class="row" style="gap:8px">' + "".join(f'<div class="card f1 col" style="align-items:center"><span class="num b" style="font-size:20px">{v}</span><span class="xs t3">{l}</span></div>' for v, l in [("9", "montantes"), ("2", "réussies"), ("−6 400", "bilan F")]) + '</div>'
 '<div class="card"><b class="sm">Réussite par palier</b>' + "".join(f'<div class="duel" style="margin-top:8px"><span class="t2">Palier {p}</span><div class="bar"><i style="width:{v}%;background:var(--lime)"></i></div><span class="num b">{v} %</span></div>' for p, v in [(1, 78), (2, 61), (3, 50), (4, 33), (5, 25)]) + '</div>'
 '<div class="card2 sm t2" style="line-height:1.5">Tu perds le plus souvent au palier 2, sur des cotes au-dessus de 1,70.</div>'))
D.append(frame(30, "Fiabilité des montantes", "Page publique : ce que donnent les montantes de tous les joueurs, sans nom.",
 topbar("Fiabilité · montantes", True) +
 '<div class="card"><div class="xs t3">Toutes les montantes terminées</div><div class="row"><b class="num" style="font-size:28px">212</b><span class="f1"></span><span class="pill g">31 % réussies</span></div></div>'
 '<div class="card"><table class="tbl"><tr><th>Paliers</th><th>Montantes</th><th>Réussies</th></tr>' + "".join(f'<tr><td>{p}</td><td>{m}</td><td class="b">{r}</td></tr>' for p, m, r in [(3, 64, "48 %"), (4, 58, "34 %"), (5, 49, "22 %"), (6, 41, "15 %")]) + '</table></div>'))
section("montante", "D · Montante", "Le mode mis en avant : des paliers qu'on voit comme un parcours, un simulateur avant de se lancer.", D)

# ---------------------------------------------------------------- E. Paris
E = []
E.append(frame(31, "Mes paris", "Onglets En cours / Réglés, bilan rapide en haut, résultat en couleur et en mots sur chaque pari.",
 topbar("Mes paris") +
 '<div class="row" style="gap:8px">' + "".join(f'<div class="card f1 col" style="align-items:center"><span class="num b {c}" style="font-size:17px">{v}</span><span class="xs t3">{l}</span></div>' for v, l, c in [("2", "en cours", ""), ("30 / 78", "gagnés", ""), ("−9 %", "rendement", "coral")]) + '</div>'
 '<div class="seg"><div class="on">En cours</div><div>Réglés</div></div>'
 '<div class="card col" style="gap:6px"><div class="row"><b class="sm f1">Pari n° 110 · simple</b><span class="pill c">● 67\'</span></div><div class="xs t2">Athletic – Espanyol · moins de 2,5 buts · 2,02</div><div class="row xs"><span class="f1 t3">Mise 1 500 F</span><b class="lime num">→ 3 030 F</b></div><div class="bar"><i style="width:74%;background:var(--green)"></i></div><div class="xs green">Gagnant pour l\'instant (1–0)</div></div>'
 '<div class="card col" style="gap:6px"><div class="row"><b class="sm f1">Pari n° 111 · simple</b><span class="pill o">17:30</span></div><div class="xs t2">Darmstadt – Heidenheim · Darmstadt ou nul · 1,76</div><div class="row xs"><span class="f1 t3">Mise 1 000 F</span><b class="num">→ 1 760 F</b></div></div>'
 '<div class="card row"><span>📊</span><b class="sm f1">Mon bilan</b><span class="t3">›</span></div>', extra=nav("Moi")))
E.append(frame(32, "Pari en cours (direct)", "Le pari en suivi : score, minute, et chaque sélection gagnante / perdante pour l'instant.",
 topbar("Pari n° 112", True) +
 '<div class="hero col" style="gap:6px;align-items:center"><span class="xs t2">Combiné · cote 3,56 · 1 000 F</span><b class="num lime" style="font-size:28px">3 560 F</b><span class="pill g">1 sur 2 déjà gagnée</span></div>'
 '<div class="card2 row"><span class="dot w">✓</span><div class="f1"><b class="sm">Darmstadt – Heidenheim</b><div class="xs t2">Darmstadt ou nul · terminé 2–1</div></div><span class="num b">1,76</span></div>'
 '<div class="card2 row"><span class="dot c">67\'</span><div class="f1"><b class="sm">Athletic – Espanyol</b><div class="xs t2">Moins de 2,5 buts · 1–0</div></div><span class="num b">2,02</span></div>'
 '<div class="card"><b class="sm">Fil du match</b><div class="xs t2" style="line-height:1.8;margin-top:4px">⚽ 52\' Williams (Athletic)<br>🟨 61\' Cabrera (Espanyol)<br>🔁 64\' Remplacement Espanyol</div></div>'))
E.append(frame(33, "Mon bilan", "Rendement, annoncé contre réalisé par marché et par championnat (colonne « annoncé » du 17/11), par cote du coupon.",
 topbar("Mon bilan", True) +
 '<div class="card col" style="gap:4px"><div class="row"><span class="t2 sm f1">Résultat net</span><b class="num coral" style="font-size:22px">−66 926 F</b></div><div class="row xs t3"><span class="f1">78 paris · 745 208 F misés</span><span>rendement −9,0 %</span></div></div>'
 '<div class="card"><b class="sm">Annoncé contre réalisé</b>' + "".join(f'<div class="duel" style="margin-top:8px;grid-template-columns:80px 1fr 64px"><span class="t2">{l}</span><div class="bar" style="position:relative"><i style="width:{r}%;background:var(--lime)"></i></div><span class="num b">{r} / {a}</span></div>' for l, a, r in [("50–60 %", 59, 59), ("60–70 %", 64, 64), ("70–80 %", 75, 66), ("80–100 %", 85, 88)]) + '<div class="xs t3" style="margin-top:6px">réalisé / annoncé</div></div>'
 '<div class="card"><table class="tbl"><tr><th>Marché</th><th>Sél.</th><th>Annoncé</th><th>Réalisé</th></tr><tr><td>Plus/moins de buts</td><td>61</td><td class="sky">72 %</td><td>75 %</td></tr><tr><td>Double chance</td><td>43</td><td class="sky">71 %</td><td class="coral b">44 %</td></tr><tr><td>Handicap européen</td><td>25</td><td class="sky">79 %</td><td class="green b">88 %</td></tr></table></div>'))
section("paris", "E · Mes paris", "Mes paris passent dans « Moi » (barre du bas) avec un bilan rapide ; le suivi en direct d'un pari devient un écran à part.", E)

# ---------------------------------------------------------------- F. Moi
F = []
F.append(frame(34, "Moi (profil)", "Tout le compte en un écran : solde fictif, Premium, raccourcis vers paris, bilan, réglages ; le jeu responsable n'est plus caché.",
 topbar("Moi") +
 '<div class="card row"><div class="av" style="width:46px;height:46px;background:#1E9E5A;font-size:16px">KO</div><div class="f1"><b>Koffi</b><div class="xs t3">🇨🇮 Côte d\'Ivoire · depuis oct. 2026</div></div><span class="pill l">Premium</span></div>'
 '<div class="row" style="gap:8px">' + "".join(f'<div class="card f1 col" style="gap:2px"><span class="xs t3">{l}</span><b class="num" style="font-size:16px">{v}</b></div>' for l, v in [("Solde fictif", "90 339 F"), ("Premium", "encore 21 j")]) + '</div>'
 '<div class="card" style="padding:4px 12px">' + "".join(f'<div class="li"><span class="ic">{i}</span><span class="f1">{t}</span><span class="t3 sm">{r}</span></div>' for i, t, r in [("🎟", "Mes paris", "2 en cours ›"), ("📊", "Mon bilan", "›"), ("🔔", "Notifications", "›"), ("⚙", "Réglages", "›"), ("🛡", "Jeu responsable", "›"), ("❓", "Aide et contact", "›")]) + '</div>', extra=nav("Moi")))
F.append(frame(35, "Réglages", "Tous les interrupteurs au même endroit : mode Montante, comparaison des moteurs, notifications, données mobiles.",
 topbar("Réglages", True) +
 '<div class="card" style="padding:4px 12px">' + "".join(f'<div class="li"><div class="f1"><div>{t}</div><div class="xs t3">{d}</div></div><span class="sw{"" if on else " off"}"></span></div>' for t, d, on in [("Mode Montante", "Ouvre l\'appli sur ta montante", True), ("Comparer les moteurs", "Moteur 2 à côté du moteur 1", False), ("Coupons du jour chaque matin", "Notification à 9 h", True), ("Économie de données", "Logos et images allégés", True)]) + '</div>'
 '<div class="card" style="padding:4px 12px">' + "".join(f'<div class="li"><span class="f1">{t}</span><span class="t3 sm">{r}</span></div>' for t, r in [("Mot de passe", "›"), ("Compte Google", "lié ›"), ("Déconnecter mes autres téléphones", "›")]) + '</div>'
 '<div class="sm coral" style="text-align:center;margin-top:4px">Supprimer mon compte</div>'))
F.append(frame(36, "Premium", "Ce que Premium débloque en cartes claires, le prix « 2 000 F pour 30 jours » et les moyens de paiement mobile.",
 topbar("Premium", True) +
 '<div class="hero col" style="gap:6px"><span class="pill l" style="width:max-content">Premium</span><b style="font-size:22px">Tous les marchés, tous les outils.</b><div class="row"><b class="num lime" style="font-size:26px">2 000 F</b><span class="t2 sm">pour 30 jours</span></div></div>'
 + "".join(f'<div class="card2 row sm"><span style="font-size:18px">{i}</span><span class="f1">{t}</span><span class="green">✓</span></div>' for i, t in [("📈", "Handicaps, mi-temps, corners, cartons"), ("✨", "Coupon intelligent et Grosse cote"), ("↗", "Suggestions de palier pour la montante"), ("☀️", "Sélections et code 1xBet des coupons du jour")]) +
 '<div class="lbl">Payer avec</div><div class="row" style="gap:6px">' + "".join(f'<div class="card f1 col" style="align-items:center;gap:3px;{"border:1.5px solid var(--lime)" if k == 0 else ""}"><b class="xs">{n}</b></div>' for k, n in enumerate(["Wave", "Orange", "MTN", "Moov"])) + '</div><div class="btn">Payer 2 000 F</div>'))
F.append(frame(37, "Paiement Wave", "Étapes numérotées, le montant et le numéro en grand, l'état « en attente de confirmation » visible.",
 topbar("Paiement Wave", True) +
 '<div class="card col" style="align-items:center;gap:4px"><span class="xs t3">À envoyer</span><b class="num" style="font-size:30px">2 000 F</b><span class="pill s">Premium · 30 jours</span></div>'
 + "".join(f'<div class="step"><span class="dot {"w" if k == 0 else "c" if k == 1 else "n"}">{k + 1}</span><span class="sm f1">{t}</span></div>' for k, t in enumerate(["Ouvre Wave", "Envoie 2 000 F au numéro FootProba", "Reviens ici : Premium s\'active à la confirmation"])) +
 '<div class="card2 row"><div class="f1"><div class="xs t3">Numéro FootProba</div><b class="num" style="font-size:17px">+225 07 XX XX XX XX</b></div><span class="pill l">Copier</span></div>'
 '<div class="card2 row sm"><span class="f1 amber">⏳ En attente de confirmation depuis 3 min</span></div><div style="flex:1"></div><div class="btn">Ouvrir Wave</div>'))
F.append(frame(38, "Notifications", "Classées par jour, avec une icône par type ; jamais une proposition de pari, silence de 23 h à 8 h rappelé en bas.",
 topbar("Notifications", True, '<span class="sm lime">Tout lu</span>') +
 '<div class="xs t3 b">AUJOURD\'HUI</div>'
 + "".join(f'<div class="card2 row" style="align-items:flex-start"><span class="li" style="border:0;padding:0"><span class="ic">{i}</span></span><div class="f1"><b class="sm">{t}</b><div class="xs t2">{d}</div></div><span class="xs t3">{h}</span></div>' for i, t, d, h in [("⚽", "But pour Athletic", "Athletic 1–0 Espanyol (52\') · ton pari n° 110", "14:20"), ("✅", "Pari n° 111 gagné", "+1 760 F fictifs", "13:05"), ("☀️", "Coupons du jour", "Les 3 coupons sont prêts", "09:00")]) +
 '<div class="xs t3 b" style="margin-top:4px">HIER</div><div class="card2 row"><span class="li" style="border:0;padding:0"><span class="ic">↗</span></span><div class="f1"><b class="sm">Montante n° 9</b><div class="xs t2">Palier 2 réussi</div></div><span class="xs t3">22:40</span></div>'
 '<div style="flex:1"></div><div class="xs t3" style="text-align:center">🌙 Silence de 23 h à 8 h (heure de ton pays)</div>'))
F.append(frame(39, "Jeu responsable", "Écran à part entière (avant : une petite fenêtre) : mises de la semaine, limite fictive choisie, pause.",
 topbar("Jeu responsable", True) +
 '<div class="card"><div class="xs t3">Mises de la semaine (fictives)</div><div class="row"><b class="num" style="font-size:24px">18 500 F</b><span class="f1"></span><span class="pill a">×2 par rapport à la semaine dernière</span></div><div class="bar" style="margin-top:8px;height:9px"><i style="width:74%;background:var(--amber)"></i></div><div class="xs t3" style="margin-top:4px">Limite choisie : 25 000 F par semaine</div></div>'
 '<div class="card" style="padding:4px 12px">' + "".join(f'<div class="li"><span class="f1">{t}</span><span class="t3 sm">{r}</span></div>' for t, r in [("Ma limite par semaine", "25 000 F ›"), ("Faire une pause", "24 h · 7 j · 30 j ›"), ("Me rappeler le temps passé", "chaque heure ›")]) + '</div>'
 '<div class="card2 sm t2" style="line-height:1.5">FootProba utilise de l\'argent fictif. Si le jeu d\'argent réel devient un problème, parle-en à un proche ou à un professionnel.</div>', tag="new"))
section("moi", "F · Moi", "« Profil » devient « Moi » : compte, Premium, paris, bilan, réglages, notifications et jeu responsable réunis.", F)

# ---------------------------------------------------------------- G. Fiabilité
G = []
G.append(frame(40, "Fiabilité", "Page de preuve : un chiffre phare, puis annoncé contre réalisé en barres doubles, par championnat et par marché.",
 topbar("Fiabilité", True) +
 '<div class="hero col" style="gap:4px"><span class="xs t2">Depuis le 1er octobre · 551 matchs</span><div class="row"><b class="num" style="font-size:30px">0,962</b><span class="f1 sm t2">erreur du moteur (log loss)<br><span class="green">meilleure que la référence simple (1,060)</span></span></div></div>'
 '<div class="seg"><div class="on">Championnats</div><div>Coupes</div><div>Sélections</div></div>'
 '<div class="card"><b class="sm">Annoncé contre réalisé</b>' + "".join(f'<div style="margin-top:8px"><div class="row xs"><span class="t2 f1">Annoncé {a} %</span><b class="num">{r} %</b></div><div class="bar" style="height:9px"><i style="width:{r}%;background:var(--lime)"></i></div></div>' for a, r in [(35, 33), (55, 57), (75, 73)]) + '</div>'
 '<div class="card row sm"><span class="f1">Par championnat</span><span class="t3">›</span></div><div class="card row sm"><span class="f1">Sélections : moteur contre cote</span><span class="t3">›</span></div>'))
G.append(frame(41, "Fiabilité du direct", "Les chances calculées pendant les matchs, vérifiées minute par minute.",
 topbar("Fiabilité · direct", True) +
 '<div class="card"><div class="xs t3">Chances en direct vérifiées</div><b class="num" style="font-size:24px">1 284</b><div class="spark" style="margin-top:8px">' + "".join(f'<i style="height:{h}%;background:var(--lime)"></i>' for h in [40, 55, 48, 62, 70, 66, 74, 80]) + '</div><div class="row xs t3"><span class="f1">0\'</span><span>90\'</span></div></div>'
 '<div class="card"><table class="tbl"><tr><th>Minute</th><th>Annoncé</th><th>Réalisé</th></tr>' + "".join(f'<tr><td>{m}</td><td class="sky">{a}</td><td class="b">{r}</td></tr>' for m, a, r in [("0–30\'", "54 %", "52 %"), ("30–60\'", "61 %", "63 %"), ("60–90\'", "72 %", "70 %")]) + '</table></div>'))
G.append(frame(42, "Moteur 1 contre moteur 2", "Visible si la comparaison est activée : erreur, argent à 1 000 F par proposition, verdict à 300 matchs.",
 topbar("Moteur 1 contre 2", True) +
 '<div class="row" style="gap:8px">' + "".join(f'<div class="card f1 col" style="gap:3px;{b}"><span class="xs t3">{n}</span><b class="num" style="font-size:22px">{v}</b><span class="xs {c}">{m}</span></div>' for n, v, m, c, b in [("Moteur 1", "0,962", "+4 200 F", "green", ""), ("Moteur 2", "0,958", "+5 900 F", "green", "border:1.5px solid var(--sky)")]) + '</div>'
 '<div class="card"><div class="row xs"><span class="t2 f1">Matchs comparés</span><b class="num">124 / 300</b></div><div class="bar" style="margin-top:6px;height:9px"><i style="width:41%;background:var(--sky)"></i></div><div class="xs t3" style="margin-top:6px">Verdict quand 300 matchs et 200 propositions seront atteints.</div></div>'))
section("fiabilite", "G · Fiabilité", "La preuve que le moteur dit vrai : un chiffre phare puis des barres simples.", G)

# ---------------------------------------------------------------- H. États + ordinateur
H = []
H.append(frame(43, "Écran verrouillé (gratuit)", "Le contenu Premium flouté derrière, la raison claire et le prix ; pas de mur noir.",
 topbar("Coupon intelligent", True) + '<div class="card" style="height:120px"></div><div class="card" style="height:120px"></div>',
 extra='<div class="lock"><span class="pill l" style="width:max-content">Premium</span><b style="font-size:20px">Le coupon composé pour toi</b><div class="t2 sm">Le moteur choisit les sélections selon ton profil, avec la cote en face.</div><div class="btn">Passer Premium · 2 000 F pour 30 jours</div></div>'))
H.append(frame(44, "Chargement, vide, erreur", "Squelettes animés au chargement, message utile quand c'est vide, bouton Réessayer quand le réseau tombe.",
 topbar("Matchs") + '<div class="card" style="height:70px;background:linear-gradient(90deg,var(--card),var(--card2),var(--card))"></div><div class="card" style="height:70px;background:linear-gradient(90deg,var(--card),var(--card2),var(--card))"></div>'
 '<div class="card col" style="align-items:center;gap:6px;text-align:center"><span style="font-size:28px">🗓</span><b class="sm">Pas de match ce jour-là</b><span class="xs t3">Les championnats reprennent vendredi.</span><span class="pill l">Voir vendredi</span></div>'
 '<div class="card col" style="align-items:center;gap:6px;text-align:center"><span style="font-size:28px">📶</span><b class="sm">Pas de connexion</b><span class="xs t3">Les cotes affichées datent de 14:10.</span><span class="pill o">Réessayer</span></div>'))
desk = ('<div style="display:flex;height:100%">'
 '<div style="width:200px;background:var(--bg2);border-right:1px solid var(--line);padding:18px 14px;display:flex;flex-direction:column;gap:6px">'
 '<div class="row" style="margin-bottom:14px"><div class="logo"><i></i></div><div class="wordmark">Foot<b>Proba</b></div></div>'
 + "".join(f'<div class="row sm" style="padding:9px 10px;border-radius:12px;{"background:var(--card2);color:var(--lime)" if k == 0 else "color:var(--t2)"}"><span>{i}</span><b>{t}</b></div>' for k, (i, t) in enumerate([("⚽", "Matchs"), ("◎", "Direct"), ("🎟", "Coupons"), ("↗", "Montante"), ("📊", "Fiabilité"), ("☺", "Moi")])) +
 '</div><div style="flex:1;padding:18px;display:flex;flex-direction:column;gap:10px;overflow:hidden">' + days +
 mrow("20:00", "Liga", "Athletic Club", "Espanyol", ("1,62", "3,90", "5,60"), ("58%", "24%", "18%"), i=0) + mrow("17:30", "2. BL", "Darmstadt", "Heidenheim", ("2,10", "3,40", "3,30"), ("44%", "27%", "29%"), sel=0, i=1) + mrow("21:00", "L1", "Lens", "Lyon", ("2,05", "3,40", "3,50"), ("47%", "27%", "26%"), i=4) +
 '</div><div style="width:300px;border-left:1px solid var(--line);padding:18px;display:flex;flex-direction:column;gap:10px"><b>Mon coupon</b>'
 '<div class="card2 col"><b class="sm">Darmstadt – Heidenheim</b><div class="row xs"><span class="t2 f1">Darmstadt</span><b class="num">2,10</b></div><div class="xs"><span class="sky b">moteur 44 %</span> <span class="amber b">cote 48 %</span></div></div>'
 '<div class="row"><span class="t2 sm f1">Gain possible</span><b class="num lime">2 100 F</b></div><div class="btn sm">Placer · 1 000 F</div></div></div>')
H.append(frame(45, "Version ordinateur", "Trois colonnes : menu, matchs, coupon toujours ouvert à droite.", desk, wide=True))
section("etats", "H · États et ordinateur", "Les écrans qu'on oublie : verrouillé, chargement, vide, erreur, et la version ordinateur.", H)

# ---------------------------------------------------------------- I. Idées
I = []
I.append(frame("I1", "Suivre mes équipes", "Une étoile sur une équipe : ses matchs remontent en haut de l'accueil, et une notification à la composition d'équipe (jamais un pari proposé).",
 topbar() + '<div class="b sm">☆ Mes équipes</div><div class="row" style="gap:8px">' + "".join(f'<div class="card col" style="align-items:center;gap:4px;width:88px">{av(n, k)}<span class="xs b">{n}</span><span class="xs t3">{w}</span></div>' for k, (n, w) in enumerate([("ASEC", "sam. 16h"), ("Athletic", "ven. 20h"), ("Lens", "ven. 21h")])) + '</div>'
 + mrow("20:00", "Liga", "Athletic Club", "Espanyol", ("1,62", "3,90", "5,60"), ("58%", "24%", "18%"), i=0, flag='<span class="pill l">☆</span>') +
 '<div class="card2 row sm"><span>🔔</span><span class="f1 t2">« Athletic : composition d\'équipe connue (titulaire : Williams). »</span></div>', tag="new", extra=nav("Matchs")))
I.append(frame("I2", "Ligue entre amis", "Un classement privé en argent fictif entre amis (code d'invitation) : on compare son bilan, pas ses mises.",
 topbar("Ligue « Bureau Plateau »", True) + '<div class="card row"><div class="f1"><div class="xs t3">Code d\'invitation</div><b class="num" style="font-size:18px;letter-spacing:2px">PLT-482</b></div><span class="pill l">Partager</span></div>'
 '<div class="card"><table class="tbl"><tr><th>#</th><th style="text-align:left">Joueur</th><th>Paris</th><th>Bilan</th></tr>' + "".join(f'<tr><td>{i}</td><td style="text-align:left">{n}</td><td>{p}</td><td class="b {c}">{b}</td></tr>' for i, n, p, b, c in [(1, "Awa", 24, "+12 %", "green"), (2, "Koffi (moi)", 31, "+4 %", "green"), (3, "Yao", 18, "−3 %", "coral"), (4, "Fatou", 9, "—", "t3")]) + '</table></div>'
 '<div class="xs t3">Classé par rendement, à partir de 10 paris. Argent fictif.</div>', tag="new"))
I.append(frame("I3", "Ma semaine en une image", "Chaque lundi, un résumé partageable : paris gagnés, meilleure cote, montante ; idéal pour le statut WhatsApp.",
 '<div style="flex:1;background:linear-gradient(170deg,#24401F,#0A0F0D 70%);border-radius:24px;padding:20px;display:flex;flex-direction:column;gap:12px">'
 '<div class="row"><div class="logo"><i></i></div><div class="wordmark">Foot<b>Proba</b></div><span class="xs t2">Semaine du 16 au 22/11</span></div>'
 '<b class="big" style="font-size:28px;line-height:1.1">Ta semaine,<br>Koffi.</b>'
 + "".join(f'<div class="card row"><span style="font-size:22px">{i}</span><div class="f1"><div class="xs t3">{l}</div><b class="num" style="font-size:18px">{v}</b></div></div>' for i, l, v in [("✅", "Paris gagnés", "5 sur 8"), ("🚀", "Plus belle cote gagnée", "4,60"), ("↗", "Montante n° 9", "palier 3 atteint")]) +
 '<div class="xs t3" style="margin-top:auto">Argent fictif · footproba.app</div></div><div class="btn">Partager sur WhatsApp</div>', tag="new"))
I.append(frame("I4", "Pourquoi ce chiffre ?", "Un appui sur une chance du moteur explique d'où elle vient : force des équipes, buts attendus, enjeu, absences connues. Transparence, sans conseil.",
 topbar("Athletic – Espanyol", True) + '<div class="card" style="height:200px"></div>',
 extra='<div class="dim"></div><div class="sheet"><div class="grab"></div><div class="row"><b class="f1">Moins de 2,5 buts : 59 %</b><span class="pill s">moteur</span></div>'
 + "".join(f'<div class="card2 row sm"><span style="font-size:16px">{i}</span><span class="f1">{t}</span><b class="{c}">{v}</b></div>' for i, t, v, c in [("⚖️", "Écart de niveau (Elo)", "Athletic +118", "t2"), ("🎯", "Buts attendus", "1,44 – 0,88", "t2"), ("🧱", "Défense d\'Athletic à domicile", "0,8 encaissé", "t2"), ("📉", "Espanyol marque peu à l\'extérieur", "0,9 / match", "t2")]) +
 '<div class="xs t3">Le moteur calcule ; la décision t\'appartient. Ce n\'est pas un conseil de pari.</div></div>', tag="new"))
I.append(frame("I5", "Économie de données", "Pour les forfaits limités : on montre ce que l'appli consomme, et un mode léger (logos et images coupés, rafraîchissement du direct moins fréquent).",
 topbar("Données mobiles", True) + '<div class="card"><div class="xs t3">Ce mois-ci</div><div class="row"><b class="num" style="font-size:28px">84 Mo</b><span class="f1"></span><span class="pill g">−46 % avec le mode léger</span></div>'
 '<div class="bar" style="margin-top:8px;height:10px"><i style="width:40%;background:var(--sky)"></i><i style="width:25%;background:var(--violet)"></i><i style="width:12%;background:var(--amber)"></i></div><div class="row xs t3" style="margin-top:4px;gap:10px"><span class="sky">● Direct</span><span style="color:var(--violet)">● Matchs</span><span class="amber">● Logos</span></div></div>'
 '<div class="card" style="padding:4px 12px">' + "".join(f'<div class="li"><div class="f1">{t}<div class="xs t3">{d}</div></div><span class="sw{"" if on else " off"}"></span></div>' for t, d, on in [("Mode léger", "Sans logos ni images", True), ("Direct toutes les 2 min", "au lieu de 30 s", True), ("Tout télécharger en Wi-Fi", "les matchs du jour d\'avance", False)]) + '</div>', tag="new"))
I.append(frame("I6", "Paiement Mobile Money", "Quand le fournisseur sera choisi : Wave, Orange Money, MTN, Moov sur le même écran, confirmation automatique.",
 topbar("Payer Premium", True) + '<div class="card col" style="align-items:center;gap:3px"><b class="num" style="font-size:28px">2 000 F</b><span class="xs t3">Premium · 30 jours</span></div>'
 + "".join(f'<div class="card row" style="{"border:1.5px solid var(--lime)" if k == 1 else ""}"><span class="av" style="width:34px;height:34px;background:{c}">{n[:2]}</span><b class="sm f1">{n}</b><span class="{"lime" if k == 1 else "t3"}">{"●" if k == 1 else "○"}</span></div>' for k, (n, c) in enumerate([("Wave", "#1DC3F0"), ("Orange Money", "#FF7900"), ("MTN MoMo", "#F7C600"), ("Moov Money", "#0056A6")])) +
 '<div class="lbl">Numéro Orange Money</div><div class="row"><div class="inp" style="width:86px">🇨🇮 +225</div><div class="inp f1">07 00 00 00 00</div></div><div class="btn">Payer 2 000 F</div>', tag="new"))
I.append(frame("I7", "Widget écran d'accueil", "Sur l'écran du téléphone, sans ouvrir l'appli : mes paris en cours et le prochain match suivi.",
 '<div style="flex:1;background:linear-gradient(160deg,#2A3B6B,#16213D);border-radius:24px;padding:16px;display:flex;flex-direction:column;gap:12px">'
 '<div class="row xs" style="color:#cdd6f5"><span class="f1">Ven. 20 novembre</span><span>14:32</span></div>'
 '<div style="background:#0A0F0DE6;border-radius:22px;padding:14px" class="col"><div class="row"><div class="logo" style="width:24px;height:24px"><i style="width:11px;height:11px;border-width:2px"></i></div><b class="sm f1">Mes paris</b><span class="pill c">● 1 en direct</span></div>'
 '<div class="row sm" style="margin-top:8px"><span class="f1">Athletic – Espanyol <span class="coral b">67\'</span></span><b class="num">1–0</b><span class="green" style="margin-left:6px">✓</span></div>'
 '<div class="row sm" style="margin-top:6px"><span class="f1 t2">Darmstadt – Heidenheim</span><b class="num">2–1</b><span class="green" style="margin-left:6px">✓</span></div></div>'
 '<div style="background:#0A0F0DE6;border-radius:22px;padding:14px" class="col"><div class="row"><span class="lime">☆</span><b class="sm f1">ASEC – Africa Sports</b><span class="xs t3">sam. 16:00</span></div></div>'
 '<div class="row" style="gap:14px;justify-content:center;margin-top:auto">' + "".join(f'<div style="width:52px;height:52px;border-radius:16px;background:{c}"></div>' for c in ["#3a4a7a", "#C4F23A", "#3a4a7a", "#3a4a7a"]) + '</div></div>', tag="new"))
I.append(frame("I8", "Défi de la semaine", "Un objectif simple chaque semaine (ex. « 3 paris simples où le moteur dépasse la cote ») avec un badge ; ça pousse à la discipline, pas à miser plus.",
 topbar("Défi de la semaine", True) + '<div class="hero col" style="gap:6px"><span class="pill l" style="width:max-content">Semaine 47</span><b style="font-size:19px">3 paris simples, mise de 1 000 F au plus</b><div class="bar" style="height:10px;margin-top:4px"><i style="width:66%;background:var(--lime)"></i></div><span class="xs t2">2 sur 3 · encore 2 jours</span></div>'
 '<div class="b sm">Mes badges</div><div class="row" style="gap:8px">' + "".join(f'<div class="card col" style="align-items:center;gap:4px;flex:1;{"opacity:.35" if k > 1 else ""}"><span style="font-size:24px">{i}</span><span class="xs b">{t}</span></div>' for k, (i, t) in enumerate([("🎯", "Discipline"), ("↗", "Palier 5"), ("📚", "100 paris")])) + '</div>'
 '<div class="xs t3">Les défis ne demandent jamais de miser plus. Argent fictif.</div>', tag="new"))
section("idees", "I · Idées de nouvelles fonctionnalités", "Huit idées qui n'existent pas encore dans l'appli, chacune avec sa maquette. Aucune ne propose de pari et aucune n'est un assistant IA.", I)


# ---------------------------------------------------------------- page
toc = "".join(f'<a href="#{sid}">{name}</a>' for sid, name, _, _ in SECTIONS)
body = []
for sid, name, lead, frames in SECTIONS:
    body.append(f'<section id="{sid}"><h2>{name}</h2><p class="lead">{lead}</p><div class="grid">{"".join(frames)}</div></section>')

palette = ('<div class="pal">' + "".join(f'<div style="background:{c};color:{t}">{n}<br>{c}</div>' for n, c, t in [
    ("Fond", "#0A0F0D", "#EEF4F0"), ("Carte", "#131C18", "#EEF4F0"), ("Action (lime)", "#C4F23A", "#0A0F0D"), ("Le moteur", "#5BC8FF", "#0A0F0D"),
    ("La cote", "#F4B740", "#0A0F0D"), ("Gagné", "#3DDC84", "#0A0F0D"), ("Perdu", "#FF6B6B", "#0A0F0D"), ("Rappel violet", "#8B6BFF", "#fff")]) + "</div>")

note = f"""<div class="note">
<h3>Le nouveau visage en bref</h3>
<ul>
<li><b>Couleurs</b> : fond vert-noir « stade de nuit », une seule couleur d'action (le vert lime), et deux couleurs qui ont un sens partout : <b class="sky">bleu = le moteur</b>, <b class="amber">ambre = la cote</b>. Vert gagné, rouge perdu. Le violet actuel reste en petite touche.</li>
<li><b>Polices</b> : Manrope pour le texte, Space Grotesk pour les chiffres (cotes, scores, montants), plus lisibles d'un coup d'œil.</li>
<li><b>Disposition</b> : nouvelle barre du bas Matchs · Direct · <b>Coupon au centre</b> · Montante · Moi. Le coupon devient un ticket permanent qu'on ouvre par le bas depuis n'importe quel écran. « Mes paris » et « Profil » sont réunis dans « Moi ».</li>
<li><b>Signature</b> : le duel <span class="sky">Moteur</span> / <span class="amber">Cote</span> en deux barres, partout où une chance est affichée.</li>
<li><b>Confort</b> : boutons de cote de 46 px (au lieu de 35), cartes vides cachées, filtres dans une feuille, squelettes de chargement.</li>
</ul>
{palette}
<h3>Ce qui ne change pas</h3>
<ul><li>Le moteur, ses chances et sa façon de choisir : intacts. Les maquettes changent l'apparence, pas les calculs.</li>
<li>Pas d'assistant IA, aucune notification ne propose un pari, silence de 23 h à 8 h, argent fictif rappelé.</li>
<li>Les chiffres des maquettes sont des exemples (repris des séances du testeur quand c'est possible).</li></ul>
</div>"""

html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FootProba : nouveau visage</title>{FONTS}<style>{CSS}</style></head><body>
<header class="top"><h1>FootProba · nouveau visage</h1><p>Proposition du 20/11/2026 : <b>45 écrans</b> de l'application refaits (tous les compartiments) et <b>8 idées</b> de nouvelles fonctionnalités, avec leur maquette. Ce sont des maquettes : rien n'est encore changé dans l'application.</p>
<div class="toc">{toc}</div></header>
{note}
{''.join(body)}
</body></html>"""

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "index.html").write_text(html, "utf-8")
print("ok", sum(len(f) for _, _, _, f in SECTIONS), "écrans")
