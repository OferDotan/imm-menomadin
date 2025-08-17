import os, re, csv, requests
from bs4 import BeautifulSoup
from datetime import datetime
from dateutil import parser as dateparser

BASE_CCY = os.getenv("BASE_CURRENCY", "ILS")
MIN_ILS = float(os.getenv("MIN_BUDGET_ILS", "20000"))
FX_API_BASE = os.getenv("FX_API_BASE_URL", "https://api.exchangerate.host")
FX_API_KEY = os.getenv("FX_API_KEY", "")

PRIORITY_AREAS = {
    "israel", "angola", "côte d’ivoire", "cote d’ivoire", "ivory coast", "europe", "european union", "eu"
}

KEYWORDS = [
    "monitoring and evaluation", "m&e", "impact evaluation", "baseline", "endline",
    "results framework", "logframe", "theory of change", "learning agenda",
    "impact measurement", "sroi", "social value",
    "monitorização e avaliação", "monitorizacao e avaliacao", "avaliação de impacto",
    "linha de base", "quadro lógico", "teoria da mudança", "medição de impacto",
    "suivi et évaluation", "suivi & évaluation", "evaluation d'impact", "évaluation d'impact",
    "étude de base", "ligne de base", "cadre logique", "théorie du changement",
    "mesure d'impact"
]

SECTOR_HINTS = [
    "higher education", "university", "community innovation", "regional development",
    "local development", "sustainability", "social program", "youth", "education",
    "health", "agriculture", "employment", "skills"
]

def t(s): return (s or "").strip()

def parse_money(text):
    if not text: return (None, None)
    txt = text.replace(",", "").replace("\u00a0", " ")
    patterns = [
        r"(USD|EUR|ILS|NIS|ZAR|AOA|GBP|€|\$|₪)\s*([0-9]+(?:\.[0-9]+)?)",
        r"([0-9]+(?:\.[0-9]+)?)\s*(USD|EUR|ILS|NIS|ZAR|AOA|GBP)"
    ]
    for p in patterns:
        m = re.search(p, txt, re.IGNORECASE)
        if m:
            if m.group(1) and str(m.group(1))[0].isalpha():
                ccy, val = m.group(1).upper(), float(m.group(2))
            else:
                val, ccy = float(m.group(1)), m.group(2).upper()
            if ccy == "NIS": ccy = "ILS"
            if ccy in ["€", "$", "₪"]:
                ccy = {"€": "EUR", "$": "USD", "₪": "ILS"}[ccy]
            return val, ccy
    return None, None

def fx_to_ils(value, currency):
    if currency is None or value is None: return (None, "unknown")
    if currency.upper() == "ILS": return (float(value), "high")
    try:
        params = {"base": currency.upper(), "symbols": "ILS"}
        if FX_API_KEY: params["api_key"] = FX_API_KEY
        r = requests.get(f"{FX_API_BASE}/latest", params=params, timeout=20)
        r.raise_for_status()
        rate = r.json()["rates"]["ILS"]
        return float(value) * float(rate), "medium"
    except Exception:
        return None, "low"

def text_contains_keywords(text, keywords):
    if not text: return False
    hay = text.lower()
    return any(k.lower() in hay for k in keywords)

def looks_like_company(name):
    if not name: return False
    name = name.lower()
    tokens = [" ltd", " limited", " inc", " gmbh", " sarl", " s.a.", " s.a", " bv", " plc", " llc", " company", " foundation"]
    return any(tok in name for tok in tokens)

def relevance_score(item):
    score = 0
    text_blob = " ".join([t(item.get("title")), t(item.get("summary")), t(item.get("full_text",""))]).lower()
    kw_hits = sum(1 for k in KEYWORDS if k in text_blob); score += min(40, kw_hits * 10)
    sector_hits = sum(1 for s in SECTOR_HINTS if s in text_blob); score += min(20, sector_hits * 5)

    country = (item.get("country") or "").lower()
    region_blob = text_blob + " " + (item.get("issuer","") or "").lower()
    if country in PRIORITY_AREAS or any(a in region_blob for a in PRIORITY_AREAS):
        score += 30
    elif country:
        score += 10

    issuer = (item.get("issuer") or "").lower()
    if any(g in issuer for g in ["world bank", "african development bank", "united nations", "ministry", "european union", "commission", "ted notice"]):
        score += 10
    if looks_like_company(issuer): score += 5

    if item.get("budget_ils") and item.get("budget_confidence") in ["high","medium"]:
        score += 10

    return max(0, min(100, score))

def fetch_ungm(query="evaluation", countries=("Israel","Angola","Côte d’Ivoire")):
    items = []
    base = "https://www.ungm.org/Public/Notice"
    for country in countries:
        try:
            r = requests.get(base, params={"Country": country, "searchText": query}, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            for row in soup.select(".search-result-row"):
                title_el = row.select_one(".notice-title")
                title = t(title_el.text if title_el else "")
                link = "https://www.ungm.org" + title_el.get("href") if title_el and title_el.has_attr("href") else None
                issuer = t((row.select_one(".agency-name") or {}).get_text(strip=True) if row.select_one(".agency-name") else "United Nations")
                snippet = t(row.get_text(" "))
                val, ccy = parse_money(snippet); ils, conf = fx_to_ils(val, ccy)
                deadline = None
                for lbl in row.select(".notice-deadline, .notice-date"):
                    try: deadline = dateparser.parse(lbl.get_text(strip=True), dayfirst=True).date().isoformat(); break
                    except Exception: pass
                items.append({"source":"UNGM","title":title,"url":link,"issuer":issuer,"country":country,"deadline":deadline,"summary":snippet[:800],"budget_value":val,"budget_currency":ccy,"budget_ils":ils,"budget_confidence":conf})
        except Exception:
            continue
    return items

def fetch_world_bank(query="evaluation", countries=("IL","AO","CI")):
    items = []
    base = "https://projects.worldbank.org/en/projects-operations/procurement"
    cmap = {"IL":"Israel","AO":"Angola","CI":"Côte d’Ivoire"}
    for cc in countries:
        try:
            r = requests.get(base, params={"searchTerm": query, "countrycode": cc}, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            for card in soup.select(".wb-card, .search-result"):
                title_el = card.select_one("a")
                title = t(title_el.text if title_el else "")
                link = (title_el.get("href") if title_el and title_el.has_attr("href") else None)
                if link and link.startswith("/"):
                    link = "https://projects.worldbank.org" + link
                snippet = t(card.get_text(" "))
                val, ccy = parse_money(snippet); ils, conf = fx_to_ils(val, ccy)
                deadline = None
                m = re.search(r"(\d{1,2} \w+ \d{4})", snippet)
                if m:
                    try: deadline = dateparser.parse(m.group(1)).date().isoformat()
                    except Exception: pass
                items.append({"source":"World Bank","title":title,"url":link,"issuer":"World Bank","country":cmap.get(cc,cc),"deadline":deadline,"summary":snippet[:800],"budget_value":val,"budget_currency":ccy,"budget_ils":ils,"budget_confidence":conf})
        except Exception:
            continue
    return items

def fetch_afdb(query="evaluation"):
    items = []
    base = "https://www.afdb.org/en/projects-and-operations/procurement"
    try:
        r = requests.get(base, timeout=30); r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        for card in soup.select(".views-row, .node--type-procurement-notice"):
            title_el = card.select_one("a"); title = t(title_el.text if title_el else "")
            link = (title_el.get("href") if title_el and title_el.has_attr("href") else None)
            if link and link.startswith("/"): link = "https://www.afdb.org" + link
            snippet = t(card.get_text(" "))
            if not text_contains_keywords(snippet + " " + title, KEYWORDS): continue
            val, ccy = parse_money(snippet); ils, conf = fx_to_ils(val, ccy)
            deadline = None
            for pat in [r"Deadline:?\s*(\d{1,2}\s+\w+\s+\d{4})", r"Closing date:?\s*(\d{1,2}\s+\w+\s+\d{4})"]:
                m = re.search(pat, snippet, re.IGNORECASE)
                if m:
                    try: deadline = dateparser.parse(m.group(1)).date().isoformat(); break
                    except Exception: pass
            items.append({"source":"AfDB","title":title,"url":link,"issuer":"African Development Bank","country":None,"deadline":deadline,"summary":snippet[:800],"budget_value":val,"budget_currency":ccy,"budget_ils":ils,"budget_confidence":conf})
    except Exception:
        pass
    return items

def fetch_israel_gov(query_terms=("הערכה","מדידה","מחקר הערכה","ייעוץ")):
    items = []
    for term in query_terms:
        try:
            r = requests.get("https://www.gov.il/he/Search", params={"q": term}, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            for res in soup.select("a.result"):
                title = t(res.get_text(" ")); link = res.get("href")
                if not link: continue
                try:
                    d = requests.get(link, timeout=20); d.raise_for_status()
                    ds = BeautifulSoup(d.text, "lxml"); full = t(ds.get_text(" "))
                    if not text_contains_keywords((title + " " + full), KEYWORDS): continue
                    val, ccy = parse_money(full); ils, conf = fx_to_ils(val, ccy)
                    deadline = None
                    m = re.search(r"(\d{2}\.\d{2}\.\d{4})", full)
                    if m:
                        try: deadline = dateparser.parse(m.group(1), dayfirst=True).date().isoformat()
                        except Exception: pass
                    items.append({"source":"Israel GOV","title":title,"url":link,"issuer":"Government of Israel","country":"Israel","deadline":deadline,"summary":full[:800],"budget_value":val,"budget_currency":ccy,"budget_ils":ils,"budget_confidence":conf})
                except Exception:
                    continue
        except Exception:
            continue
    return items

def fetch_eu_ted_stub(): return []
def fetch_civ_portal_stub(): return []

FETCHERS = [fetch_ungm, fetch_world_bank, fetch_afdb, fetch_israel_gov, fetch_eu_ted_stub, fetch_civ_portal_stub]

def run_pipeline():
    rows = []
    for fetcher in FETCHERS:
        try: rows.extend(fetcher())
        except Exception: continue

    cleaned = []
    for it in rows:
        if not it.get("budget_ils"):
            txt = (it.get("summary") or "") + " " + (it.get("title") or "")
            if len(txt.split()) < 120: continue
            it["budget_ils"] = None; it["budget_confidence"] = "low"
        if it.get("budget_ils") is not None and it.get("budget_ils") < MIN_ILS: continue
        if not text_contains_keywords((it.get("title") or "") + " " + (it.get("summary") or ""), KEYWORDS): continue
        it["fit_score"] = relevance_score(it)
        cleaned.append(it)

    cleaned.sort(key=lambda x: x.get("fit_score", 0), reverse=True)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out_path = f"opportunities_{ts}.csv"
    columns = ["source","title","issuer","country","deadline","budget_value","budget_currency","budget_ils","budget_confidence","fit_score","url","summary"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns); w.writeheader()
        for it in cleaned: w.writerow({k: it.get(k) for k in columns})
    print(f"Saved {len(cleaned)} opportunities → {out_path}")

if __name__ == "__main__":
    run_pipeline()
