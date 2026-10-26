"""Opcional: espelha os resultados numa planilha do Google Sheets.
Só roda se os segredos GSHEET_ID e GOOGLE_SERVICE_ACCOUNT_JSON existirem."""
import json
import os


def enviar(rows: list[dict], cols: list[str]) -> bool:
    sid, cred = os.getenv("GSHEET_ID"), os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not (sid and cred):
        return False
    import gspread
    ws = gspread.service_account_from_dict(json.loads(cred)).open_by_key(sid).sheet1
    if not ws.row_values(1):
        ws.append_row(cols)
    ws.append_rows([[float(r[c]) if c == "preco" else r[c] for c in cols] for r in rows],
                   value_input_option="RAW")
    return True
