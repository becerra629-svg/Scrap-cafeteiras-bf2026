"""Coleta de resultados de busca com Playwright (navegador headless)."""
import random
import re
import time
from pathlib import Path
from urllib.parse import quote_plus

from parsing import norm

SITES = {
    "mercadolivre": {
        "nome": "Mercado Livre",
        "url": "https://lista.mercadolivre.com.br/{hifen}",
        "cards": ["li.ui-search-layout__item", "div.poly-card"],
        "title": ["a.poly-component__title", "h2.ui-search-item__title", "h3 a", "h2"],
        "price": [".poly-price__current .andes-money-amount",
                  ".ui-search-price__second-line .andes-money-amount",
                  ".andes-money-amount:not(.andes-money-amount--previous)"],
        "link": ["a.poly-component__title", "a.ui-search-link", "a[href]"],
        "link_pattern": r"(mercadolivre|mercadolibre)\.com\.br/.*(MLB|/p/)",
    },
    "amazon": {
        "nome": "Amazon",
        "url": "https://www.amazon.com.br/s?k={mais}",
        "cards": ['div[data-component-type="s-search-result"]'],
        "title": ["h2"],
        "price": ["span.a-price:not(.a-text-price) .a-offscreen", "span.a-price .a-offscreen"],
        "link": ["h2 a", "a.a-link-normal.s-no-outline"],
        "link_pattern": r"amazon\.com\.br/.*/dp/",
    },
    "casasbahia": {
        "nome": "Casas Bahia",
        "url": "https://www.casasbahia.com.br/{hifen}/b",
        "cards": ['[data-testid="product-card"]', 'div[class*="product-card"]'],
        "title": ['[data-testid="product-title"]', "h2", "h3"],
        "price": ['[data-testid="price-value"]', '[class*="price"]'],
        "link": ["a[href]"],
        "link_pattern": r"casasbahia\.com\.br/.+/p/\d+",
    },
    "magalu": {
        "nome": "Magazine Luiza",
        "url": "https://www.magazineluiza.com.br/busca/{mais}/",
        "cards": ['[data-testid="product-card-container"]'],
        "title": ['[data-testid="product-title"]', "h2"],
        "price": ['[data-testid="price-value"]', '[data-testid="price-default"]'],
        "link": ["a[href]"],
        "link_pattern": r"magazineluiza\.com\.br/.+/p/",
    },
}

# Roda dentro da página. Primeiro tenta os seletores do site; se não achar
# nada, usa uma heurística genérica (links de produto + texto com "R$").
EXTRACT_JS = r"""
(cfg) => {
  const txt = el => el ? ((el.innerText || '').trim() || (el.textContent || '').trim()) : '';
  const first = (root, sels) => { for (const s of sels) { const e = root.querySelector(s); if (e) return e; } return null; };
  const readPrice = el => {
    if (!el) return '';
    const fr = el.querySelector('.andes-money-amount__fraction');
    if (fr) { const c = el.querySelector('.andes-money-amount__cents'); return 'R$ ' + txt(fr) + ',' + (c ? txt(c) : '00'); }
    return txt(el);
  };
  let cards = [];
  for (const s of cfg.cards) { cards = [...document.querySelectorAll(s)]; if (cards.length) break; }
  let items = [];
  for (const c of cards) {
    const a = first(c, cfg.link), t = first(c, cfg.title), p = first(c, cfg.price);
    items.push({
      title: txt(t) || (a && (a.getAttribute('title') || a.getAttribute('aria-label'))) || '',
      price: readPrice(p), cardText: txt(c).slice(0, 700), href: a ? a.href : ''
    });
  }
  if (!items.length || items.every(i => !i.href)) {
    items = [];
    const re = new RegExp(cfg.linkPattern), seen = new Set();
    for (const a of document.querySelectorAll('a[href]')) {
      if (!re.test(a.href)) continue;
      let c = a, d = 0;
      while (c.parentElement && d < 7 && !/R\$/.test(c.innerText || '')) { c = c.parentElement; d++; }
      const ct = c.innerText || '';
      if (!/R\$/.test(ct) || ct.length > 1500 || seen.has(c)) continue;
      seen.add(c);
      const lines = ct.split('\n').map(l => l.trim())
        .filter(l => l.length >= 12 && !/R\$|frete|parcel|desconto|% off|avalia|vendid/i.test(l));
      lines.sort((x, y) => y.length - x.length);
      items.push({ title: a.getAttribute('title') || a.getAttribute('aria-label') || lines[0] || '',
                   price: '', cardText: ct.slice(0, 700), href: a.href });
    }
  }
  return items;
}
"""

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def build_url(site: str, query: str) -> str:
    q = norm(query)
    return SITES[site]["url"].format(hifen=q.replace(" ", "-"), mais=quote_plus(q))


def new_context(playwright):
    browser = playwright.chromium.launch(
        headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        user_agent=UA, locale="pt-BR", timezone_id="America/Sao_Paulo",
        viewport={"width": 1366, "height": 900},
        extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5"},
    )
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return browser, ctx


def fetch_results(ctx, site: str, query: str, debug_dir: Path) -> list[dict]:
    """Abre a busca e devolve itens brutos: title, price, cardText, href."""
    cfg = SITES[site]
    url = build_url(site, query)
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_selector(", ".join(cfg["cards"]), timeout=15000)
        except Exception:
            pass  # a heurística genérica ainda pode funcionar
        for _ in range(5):  # rolar para carregar itens "lazy"
            page.mouse.wheel(0, 1600)
            page.wait_for_timeout(700)
        items = page.evaluate(EXTRACT_JS, {
            "cards": cfg["cards"], "title": cfg["title"], "price": cfg["price"],
            "link": cfg["link"], "linkPattern": cfg["link_pattern"]})
        if not items:
            slug = re.sub(r"\W+", "_", norm(query))
            page.screenshot(path=str(debug_dir / f"{site}_{slug}.png"), full_page=False)
            (debug_dir / f"{site}_{slug}.html").write_text(page.content(), encoding="utf-8")
            title = page.title()
            raise RuntimeError(f"0 resultados (título da página: {title!r}) — possível bloqueio ou seletor desatualizado")
        return items
    finally:
        page.close()


def pause():
    time.sleep(random.uniform(3, 7))
