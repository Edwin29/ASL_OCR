const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { chromium } = require('C:/Users/왕원철/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async () => {
  const input = path.resolve(process.argv[2]);
  const out = path.resolve(process.argv[3]);
  fs.mkdirSync(out, {recursive: true});
  const content = fs.readFileSync(input, 'utf8');
  const diagrams = [...content.matchAll(/```mermaid\r?\n([\s\S]*?)```/g)].map(m => m[1]);
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  const results = [];
  try {
    for (let i = 0; i < diagrams.length; i++) {
      const page = await browser.newPage({viewport: {width: 1800, height: 1200}});
      await page.setContent('<html><body style="margin:24px;background:white"></body></html>');
      await page.addScriptTag({path: path.join(__dirname, 'mermaid-11.12.0.min.js')});
      const result = await page.evaluate(async ({source, id}) => {
        mermaid.initialize({startOnLoad: false, securityLevel: 'strict', theme: 'default'});
        try {
          await mermaid.parse(source);
          const rendered = await mermaid.render(id, source);
          document.body.innerHTML = rendered.svg;
          return {passed: true, svg: rendered.svg};
        } catch (e) {return {passed: false, error: String(e)};}
      }, {source: diagrams[i], id: 'diagram'+i});
      if (result.passed) {
        fs.writeFileSync(path.join(out, `diagram-${i+1}.svg`), result.svg);
        await page.locator('svg').screenshot({path: path.join(out, `diagram-${i+1}.png`)});
      }
      delete result.svg;
      results.push({diagram: i+1, ...result});
      await page.close();
    }
  } finally {await browser.close();}
  const report = {renderer: 'mermaid@11.12.0', browser: 'Microsoft Edge headless', input,
    sha256: crypto.createHash('sha256').update(content).digest('hex'), results};
  fs.writeFileSync(path.join(out, 'render-results.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  process.exitCode = results.every(r => r.passed) ? 0 : 1;
})().catch(e => {console.error(e);process.exitCode=1;});
