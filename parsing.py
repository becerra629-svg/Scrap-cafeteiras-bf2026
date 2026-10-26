"""Funções de limpeza: preço, voltagem, cor, link e filtro de produto."""
import re
import unicodedata
from urllib.parse import urlsplit, parse_qs, unquote


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


# ---------- preço ----------
_PRICE_RE = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)")
_IGNORE_LINE = re.compile(r"\d+\s*x\b|parcel|juros|frete|economi|desconto|cupom|cashback|\boff\b")


def _to_float(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def extract_price(text: str, minimo: float = 0) -> float | None:
    """Menor preço 'cheio' encontrado no texto (ignora parcelas, frete, descontos).
    Se o site mostra preço no Pix e no cartão, fica o menor."""
    text = re.sub(r"R\$\s*\n\s*", "R$ ", text or "")
    found = []
    for line in text.splitlines():
        if _IGNORE_LINE.search(line.lower()):
            continue
        for m in _PRICE_RE.finditer(line):
            try:
                v = _to_float(m.group(1))
            except ValueError:
                continue
            if v >= minimo:
                found.append(v)
    return min(found) if found else None


# ---------- voltagem ----------
_VOLT = re.compile(
    r"(?<![\d.,])(110|127|220)(?=\s*(?:v\b|volts?\b|/\s*(?:110|127|220)\s*v\b))"
)


def extract_voltage(title: str) -> str:
    t = norm(title)
    if "bivolt" in t:
        return "Bivolt"
    nums = {("110V" if n in ("110", "127") else "220V") for n in _VOLT.findall(t)}
    if len(nums) == 2:
        return "110V/220V"
    return nums.pop() if nums else "N/D"


# ---------- cor ----------
_COLORS = [
    ("Preto", r"preto|preta|black|licorice|piano"),
    ("Branco", r"branco|branca|white|coconut"),
    ("Vermelho", r"vermelho|vermelha|red|spicy|cherry|rosso"),
    ("Azul", r"azul|blue"),
    ("Cinza", r"cinza|grey|gray|grafite|titanio|titanium"),
    ("Prata", r"prata|silver|inox"),
    ("Verde", r"verde|green|lime|mint|aqua"),
    ("Amarelo", r"amarelo|amarela|yellow|mango"),
    ("Rosa", r"rosa|pink"),
    ("Laranja", r"laranja|orange"),
    ("Dourado", r"dourado|gold"),
    ("Bege", r"bege|creme|cream"),
    ("Marrom", r"marrom|brown"),
]


def extract_color(title: str) -> str:
    t = norm(title)
    best, best_pos = "N/D", 10**9
    for label, pat in _COLORS:
        m = re.search(rf"\b({pat})\b", t)
        if m and m.start() < best_pos:
            best, best_pos = label, m.start()
    return best


# ---------- link ----------
def canonical_link(site: str, href: str) -> str:
    if not href:
        return ""
    if site == "amazon":
        m = re.search(r"/dp/([A-Z0-9]{10})", unquote(unquote(href)))
        if m:
            return f"https://www.amazon.com.br/dp/{m.group(1)}"
    p = urlsplit(href)
    if p.netloc.startswith("click") and "url" in parse_qs(p.query):  # anúncios patrocinados
        return canonical_link(site, parse_qs(p.query)["url"][0])
    return f"{p.scheme}://{p.netloc}{p.path}"


# ---------- filtro de produto ----------
def match_product(title: str, produtos: list, excluir_global: list) -> str | None:
    t = norm(title)
    if any(re.search(p, t) for p in excluir_global):
        return None
    for prod in produtos:
        if all(re.search(p, t) for p in prod["incluir"]) and not any(
            re.search(p, t) for p in prod.get("excluir", [])
        ):
            return prod["nome"]
    return None
