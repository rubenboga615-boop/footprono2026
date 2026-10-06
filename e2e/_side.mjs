// Côte à côte : maquette (gauche) et application (droite), à la même échelle.
import { chromium } from 'playwright';
const [SP, pairs] = [process.argv[2], process.argv.slice(3)];
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const p = await b.newPage({ viewport: { width: 820, height: 870 }, deviceScaleFactor: 2 });
for (const pair of pairs) {
  const [mock, app, out] = pair.split(':');
  await p.setContent(`<body style="margin:0;background:#222;display:flex;gap:20px;padding:13px 10px;font:12px sans-serif;color:#fff">
    <div><img src="file://${SP}/cmp/${mock}" width="390"><div>maquette</div></div>
    <div><img src="file://${SP}/cmp/${app}" width="390"><div>application</div></div></body>`);
  await p.waitForTimeout(400);
  await p.screenshot({ path: `${SP}/cmp/${out}` });
}
await b.close();
