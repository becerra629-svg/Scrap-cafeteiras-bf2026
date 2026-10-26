# Monitor de preços – Cafeteiras

Robô (GitHub Actions) que consulta Mercado Livre, Amazon, Casas Bahia e Magazine Luiza
a cada 2 dias, grava o histórico em `docs/data/precos.csv` e publica um painel em GitHub Pages.

- `config.yaml` — produtos, buscas e filtros (edite aqui para incluir novos modelos)
- `main.py` / `scraper.py` / `parsing.py` — coleta e limpeza
- `docs/index.html` — painel (tabela, filtros e gráfico de histórico)
- `.github/workflows/scraper.yml` — agendamento
- `sheets.py` — envio opcional para Google Sheets

Rodar manualmente: aba **Actions → Coletar preços → Run workflow**.
Se um site falhar, veja o log da execução e baixe o artefato **debug** (print + HTML da página).
