// Parcours de bout en bout : vraie API + vraie application web, dans Chromium.
//   E2E_URL=http://127.0.0.1:8000/app/ node e2e/app.test.mjs
// La base doit avoir été préparée par e2e/seed.py (matchs à venir, prédictions, cotes).
import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const URL = (process.env.E2E_URL || 'http://127.0.0.1:8000/app/') + '?e2e';
const SHOTS = process.env.E2E_SHOTS || '';
const browser = await chromium.launch(
  process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
);
// Langue explicite : sans langue système (LANG vide, cas des machines d'intégration),
// Chromium annonce « en-US@posix », que le moteur Flutter web refuse au démarrage.
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, locale: 'fr-FR' });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));

let step = 0;
async function check(name, fn) {
  step += 1;
  process.stdout.write(`${step}. ${name} … `);
  try {
    await fn();
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/${String(step).padStart(2, '0')}.png` });
    console.log('ok');
  } catch (e) {
    console.log('ÉCHEC');
    const buttons = await page.$$eval('flt-semantics[role=button]', (es) =>
      es.map((e) => `${e.textContent.slice(0, 30)} [${e.getAttribute('aria-disabled') ?? ''}]`),
    );
    console.log(`boutons à l'écran : ${buttons.join(' | ')}`);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/echec-${step}.png` });
    await browser.close();
    throw e;
  }
}
// Les écrans précédents restent dans la page sous l'écran ouvert : l'élément de
// l'écran au premier plan est le dernier du document.
// Un texte peut être un nœud de texte ou le nom (aria-label) d'un groupe : les deux
// sont ce qu'un lecteur d'écran annonce.
const text = (t, o = {}) => page.getByText(t, o).or(page.getByLabel(t, o)).first();
const button = (name) => page.getByRole('button', { name, disabled: false }).last();
// Présent dans l'arbre d'accessibilité de l'écran (les nœuds Flutter sont transparents).
const visible = (loc, timeout = 15000) => loc.waitFor({ state: 'attached', timeout });
// Saisie comme un utilisateur : clic dans le champ, tout sélectionner, taper.
async function type(label, value) {
  await page.getByLabel(label).first().click();
  await page.keyboard.press('End');
  for (let i = 0; i < 30; i += 1) await page.keyboard.press('Backspace');
  await page.keyboard.type(value, { delay: 10 });
}
const nav = (label) => button(new RegExp(`^${label}`)).click();
const phone = `+2250${String(Date.now()).slice(-9)}`;

await check('inscription', async () => {
  await page.goto(URL);
  await visible(text('Bon retour'), 30000);
  await text('Créer un compte').click();
  await visible(text('Nom affiché'));
  await type('Nom affiché', 'Testeur E2E');
  await type('Numéro de téléphone', phone);
  await type('Mot de passe', 'motdepasse-e2e');
  await page.getByRole('checkbox').first().click();
  await button(/Créer mon compte/).click();
});

await check('matchs à venir avec probabilités du moteur', async () => {
  await visible(text(/^Matchs (à venir|du jour)/));
  // Chaque carte de match est un bouton : son nom contient les probabilités.
  await visible(button(/1 · \d+.*N · \d+.*2 · \d+/s));
  await visible(button(/Les deux marquent · \d+/));
});

await check('match : probabilités et cote réelle ajoutée au coupon', async () => {
  await button(/ vs /).click();
  await visible(text('Résultat du match'));
  await button(/1xBet/).click();
  await visible(text('Ajouté au coupon'));
  await button('Retour').click();
});

await check('coupon : pari placé, gain calculé', async () => {
  await nav('Coupon');
  await visible(text('Mon coupon · 1 sélection'));
  await visible(text('Gain possible'));
  await button('Valider le coupon').click();
  await visible(text(/Pari placé/));
});

await check('bookmaker : pari en cours, solde débité', async () => {
  await nav('Bookmaker');
  await visible(text('Mes paris'));
  await visible(text('99 000 F CFA'));
});

await check('profil : essai Premium de 7 jours', async () => {
  await nav('Profil');
  await visible(text('FootProno Premium'));
  await visible(text('Actif'));
});

await check('fiabilité : page publique', async () => {
  await text('Fiabilité du modèle').click();
  await visible(text(/Annoncé contre réalisé/));
  await visible(text('Backtest'));
  await button('Retour').click();
});

await check('montante : lancement puis suggestions du palier 1', async () => {
  await nav('Montante');
  await button('Lancer la montante').click();
  await visible(text(/Montante lancée/));
  // Bouton sous le tableau : faire défiler l'écran (Flutter ne suit pas le DOM).
  await page.mouse.move(195, 400);
  await page.mouse.wheel(0, 1200);
  await page.waitForTimeout(800);
  await button('Choisir le pari').click();
  await visible(text(/Pari du/));
  await visible(text('Suggestions'));
});

assert.deepEqual(errors, [], `erreurs JavaScript : ${errors.join(' | ')}`);
await browser.close();
console.log(`Parcours complet : ${step} étapes réussies.`);
