"""Monitor de preços de cafeteiras. Uso: python main.py  (FORCE=1 ignora o intervalo)."""
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from playwright.sync_api import sync_playwright

import scraper
from parsing import (canonical_link, extract_color, extract_price,
                     extract_voltage, match_product)

ROOT = Path(__file__).parent
DATA = ROOT / "docs" / "data"
CSV_PATH = DATA / "precos.csv"
STATUS_PATH = DATA / "status.json"
DEBUG = ROOT / "debug"
COLS = ["data_hora", "data", "site", "modelo", "titulo", "cor", "voltagem", "preco", "link"]


def ran_recently(horas: float) -> bool:
    if not STATUS_PATH.exists():
        return False
    last = json.loads(STATUS_PATH.read_text(encoding="utf-8")).get("ultima_execucao_utc")
    if not last:
        return False
    delta = datetime.now(timezone.utc) - datetime.fromisoformat(last)
    return delta.total_seconds() < horas * 3600


def collect(cfg: dict) -> tuple[list[dict], dict]:
    now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    rows, status = [], {}
    minimo = cfg.get("preco_minimo", 0)
    with sync_playwright() as pw:
        browser, ctx = scraper.new_context(pw)
        for site in cfg["sites"]:
            nome = scraper.SITES[site]["nome"]
            vistos, erros, n_site = set(), [], 0
            for prod in cfg["produtos"]:
                for busca in prod["buscas"]:
                    try:
                        itens = scraper.fetch_results(ctx, site, busca, DEBUG)
                    except Exception as e:  # um site com problema não derruba os outros
                        erros.append(f"{busca}: {e}")
                        print(f"[{nome}] ERRO em '{busca}': {e}")
                        scraper.pause()
                        continue
                    for it in itens:
                        modelo = match_product(it["title"], cfg["produtos"], cfg["excluir_global"])
                        link = canonical_link(site, it["href"])
                        preco = extract_price(it["price"], minimo) or extract_price(it["cardText"], minimo)
                        if not (modelo and link and preco) or (site, link) in vistos:
                            continue
                        vistos.add((site, link))
                        n_site += 1
                        rows.append({
                            "data_hora": now.isoformat(timespec="minutes"),
                            "data": now.strftime("%Y-%m-%d"),
                            "site": nome, "modelo": modelo, "titulo": it["title"][:200],
                            "cor": extract_color(it["title"]), "voltagem": extract_voltage(it["title"]),
                            "preco": f"{preco:.2f}", "link": link})
                    print(f"[{nome}] '{busca}': {len(itens)} itens brutos")
                    scraper.pause()
            status[nome] = {"anuncios": n_site, "erros": erros[:3]}
        browser.close()
    return rows, status


def save(rows: list[dict], status: dict):
    DATA.mkdir(parents=True, exist_ok=True)
    novo = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if novo:
            w.writeheader()
        w.writerows(rows)
    STATUS_PATH.write_text(json.dumps({
        "ultima_execucao_utc": datetime.now(timezone.utc).isoformat(),
        "ultima_execucao_local": datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M"),
        "sites": status}, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    if os.getenv("FORCE") != "1" and ran_recently(cfg["intervalo_minimo_horas"]):
        print("Última coleta recente demais; nada a fazer.")
        return 0
    DEBUG.mkdir(exist_ok=True)
    rows, status = collect(cfg)
    if not rows:
        print("Nenhum anúncio coletado em nenhum site — não gravei nada.")
        return 1
    save(rows, status)
    try:
        from sheets import enviar
        if enviar(rows, COLS):
            print("Enviado ao Google Sheets.")
    except Exception as e:
        print(f"Aviso: falha ao enviar ao Google Sheets: {e}")
    print(f"OK: {len(rows)} anúncios gravados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
