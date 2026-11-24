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
// Fichiers de Firebase (connexion Google) non chargés : réseau, pas l'application
// (machine de test sans accès à www.gstatic.com).
page.on('pageerror', (e) => {
  if (!String(e).includes('gstatic.com/firebasejs')) errors.push(String(e));
});

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
  // Accueil de la maquette du 07/11/2026 : « Créer mon compte gratuit », puis Google ou le
  // numéro sur l'écran suivant (sans Google : directement le formulaire).
  await button('Créer mon compte gratuit').click();
  if (!(await text('Nom affiché').isVisible().catch(() => false))) {
    await button('Numéro de téléphone').click();
  }
  await visible(text('Nom affiché'));
  await type('Nom affiché', 'Testeur E2E');
  await type('Numéro de téléphone', phone);
  await type('Mot de passe', 'motdepasse-e2e');
  await page.getByRole('checkbox').first().click();
  await button(/Créer mon compte/).click();
});

// Nouveau visage (maquettes 12-nouveau-visage, 20/11/2026) : barre du bas Aujourd'hui · Matchs
// · Créer · Paris · Moi ; le parcours suit les mêmes étapes qu'avant.
await check('tableau de bord, puis matchs avec probabilités du moteur', async () => {
  await visible(text('Tableau de bord'));
  await nav('Matchs');
  // Une carte par match (maquette 6) : un bouton dont le nom contient les chances 1, N, 2.
  await visible(button(/\d+\s?%.*\d+\s?%.*\d+\s?%/s));
});

await check('match : probabilités et cote réelle ajoutée au coupon', async () => {
  await button(/\d+\s?%.*\d+\s?%.*\d+\s?%/s).first().click();
  await visible(text(/résultat du match/i));
  // Cote 1xBet sous chaque issue : le bouton porte la cote.
  await page.getByRole('button', { name: /^\d+,\d+/ }).first().click();
  await visible(text('Ajouté au coupon'));
  await button('Retour').click();
});

await check('coupon : pari placé, gain calculé', async () => {
  await nav('Créer');
  await button(/^Mon coupon/).click();
  // Le bas du coupon peut être sous l'écran (la liste ne construit que ce qui est proche).
  await page.mouse.move(200, 400);
  await page.mouse.wheel(0, 800);
  await page.waitForTimeout(800);
  // Gain et risque côte à côte (maquette 13), puis « Placer · 1 000 F ».
  await visible(text(/Si ça passe/));
  await button(/^Placer/).click();
  // Récapitulatif avant le pari (maquette N5).
  await button(/Confirmer/).click();
  await visible(text(/Pari placé/));
});

await check('mes paris : pari en cours, solde débité', async () => {
  await nav('Paris');
  await visible(text(/En cours/));
  await visible(text(/99\s000/));
});

await check('moi : version gratuite, pas d\'essai automatique', async () => {
  await nav('Moi');
  await visible(text('Version gratuite'));
  await visible(text(/Passer Premium/));
});

await check('fiabilité : page publique', async () => {
  await text('Fiabilité du moteur').click();
  await visible(text(/Simulation/));
  await visible(text(/Depuis le lancement/));
  await button('Retour').click();
});

await check('montante : lancement, suggestions réservées à Premium', async () => {
  await nav('Créer');
  await button(/^Montante/).click();
  await button('Créer la montante').click();
  // Montante lancée (maquette 15) : palier en cours.
  await visible(text(/palier 1 sur/i));
  // Suggestions du moteur : réservées à Premium, avec le bouton d'abonnement.
  await button('Voir les paris proposés').click();
  await visible(text(/Premium/));
});

assert.deepEqual(errors, [], `erreurs JavaScript : ${errors.join(' | ')}`);
await browser.close();
console.log(`Parcours complet : ${step} étapes réussies.`);
