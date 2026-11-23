from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path('.scratch/remediation-verification')
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for theme in ('light', 'dark'):
        page = browser.new_page(viewport={'width': 900, 'height': 600}, color_scheme=theme)
        page.goto('http://127.0.0.1:5179/login', wait_until='networkidle')
        page.evaluate('''async theme => {
          document.documentElement.dataset.theme = theme;
          document.getElementById('root').style.display = 'none';
          const React = (await import('/node_modules/.vite/deps/react.js')).default;
          const { createRoot } = (await import('/node_modules/.vite/deps/react-dom_client.js')).default;
          const { EntityCard } = await import('/src/shared/components/EntityCard.tsx');
          const host = document.createElement('div'); host.id = 'visual-check';
          host.style.cssText = 'position:fixed;z-index:10000;inset:20px auto auto 20px;width:360px';
          document.body.appendChild(host);
          createRoot(host).render(React.createElement(EntityCard, {title: React.createElement('a', {href:'#detail'}, 'Entity title'), footerNote: 'Footer'}, 'Card body'));
        }''', theme)
        heading = page.locator('#visual-check h2')
        link = heading.locator('a')
        link.wait_for()
        color = link.evaluate('(el) => getComputedStyle(el).color')
        parent = heading.evaluate('(el) => getComputedStyle(el).color')
        assert color == parent, (theme, color, parent)
        assert link.is_visible()
        current = page.locator('#visual-check').screenshot(path=str(out / f'entity-card-{theme}.png'))
        link.evaluate("el => el.style.setProperty('color', 'inherit', 'important')")
        previous = page.locator('#visual-check').screenshot()
        assert current == previous, f'{theme}: visual differs from former inherited important color'
        print(f'{theme}: link={color}, heading={parent}, visible=True')
        page.close()
    browser.close()
