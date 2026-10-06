import { chromium } from 'playwright';
const SP = process.argv[2];
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const p = await b.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
for (const n of ['Main','Match','Coupon','CouponIntelligent','CouponsDuJour','Montante','Bookmaker','Profil','Fiabilite']) {
  await p.goto('file://' + SP + '/app-v2/project/' + n + '.dc.html'); await p.waitForTimeout(500);
  await p.screenshot({ path: SP + '/cmp/m-' + n + '.png' });
}
await b.close();
