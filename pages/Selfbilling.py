import hashlib
import io
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

# GEEN st.set_page_config hier (dat gebeurt in Home.py)
st.title("🧾 Self-billing per leverancier")
st.caption("Upload leveranciers-Excel(s), bereken automatisch de self-billing en exporteer het resultaat.")

# -------------------- CONFIG --------------------
CANON_COLS = [
    "Ophaaldatum", "Locatienummer", "Debiteurnummer", "Klantnaam",
    "Leverancier", "Dienst logistiek", "Uitgevoerd", "Gepland",
    "Kilogram",
    "Status", "Productomschrijving", "Afvalstroom", "Straat",
    "Huisnr", "Postcode", "Plaats", "Verantwoordelijke partij"
]

DEFAULT_PRICING_ALL = pd.DataFrame([
    {"leverancier": "Recycling-Continue", "tarieftype": "per_stop", "prijs": 4.00, "afvalstroom": ""},
    {"leverancier": "Gianluca",            "tarieftype": "per_stop", "prijs": 4.10, "afvalstroom": ""},
    {"leverancier": "Revema",              "tarieftype": "per_stop", "prijs": 4.00, "afvalstroom": ""},
    #{"leverancier": "Gogogo",             "tarieftype": "per_stop", "prijs": 3.00, "afvalstroom": ""},  # gestopt
    {"leverancier": "Papierhandel Jansen", "tarieftype": "per_kiep", "prijs": 3.50, "afvalstroom": ""},
    {"leverancier": "Visser Assen",        "tarieftype": "per_kiep", "prijs": 4.00,  "afvalstroom": "Papier/Karton"},
    {"leverancier": "Visser Assen",        "tarieftype": "per_kiep", "prijs": 12.50, "afvalstroom": "Vertrouwelijk papier"},
    {"leverancier": "Schuman",             "tarieftype": "per_kiep", "prijs": 0.00,  "afvalstroom": ""},
    {"leverancier": "Van Bruchem",         "tarieftype": "per_kiep", "prijs": 4.00,  "afvalstroom": ""},
    #{"leverancier": "N.V. Reinigingsdiensten Rd4", "tarieftype": "per_kiep", "prijs": 17.14, "afvalstroom": ""},
    {"leverancier": "Rowill", "tarieftype": "per_kiep", "prijs": 150.00,  "afvalstroom": ""},
    # Bal: EUR 3,50 per stop. Meerdere ledigingen op dezelfde dag en locatie
    # leveren samen een stop op, dus niet per container vermenigvuldigen.
    {"leverancier": "Bal Recycling",       "tarieftype": "per_stop", "prijs": 3.50,  "afvalstroom": ""},
    # Meertens: per lediging. Swill EUR 18,50, frituurvet EUR 0,00
    # (de regel met afvalstroom gaat voor op de algemene regel).
    {"leverancier": "Meertens",            "tarieftype": "per_kiep", "prijs": 18.50, "afvalstroom": ""},
    {"leverancier": "Meertens",            "tarieftype": "per_kiep", "prijs": 0.00,  "afvalstroom": "Frituurvet"},
])

SUPPLIERS = [
    "Recycling-Continue", "Gianluca", "Revema",  #"Gogogo" gestopt
    "Papierhandel Jansen", "Visser Assen", "Schuman", "Van Bruchem", "Rowill", #"N.V. Reinigingsdiensten Rd4"
    "Bal Recycling", "Meertens",
]

# Zoekterm per leverancier voor de kolom 'Leverancier' in het orderbestand.
# Nodig waar de naam in SUPPLIERS afwijkt van de naam in de MSN-export
# (bv. " J. Meertens & Zn. B.V." en "Bal Recycling B.V.").
SUPPLIER_MATCH = {
    "Bal Recycling": "bal recycling",
    "Meertens": "meertens",
}

# Leveranciers die per stop betaald worden: meerdere orderregels op dezelfde
# dag en hetzelfde locatienummer leveren samen één stopvergoeding op.
PER_STOP_DEDUP_SUPPLIERS = (
    "recycling-continue", "gianluca", "revema", "bal recycling",
)

SCHUMAN_PRICES = {
    ("240L", "Restafval"): 8.93,
    ("240L", "Papier/Karton"): 4.70,
    ("360L", "Restafval"): 12.08,
    ("360L", "Papier/Karton"): 4.70,
    ("500L", "Restafval"): 13.13,
    ("660L", "Restafval"): 16.28,
    ("660L", "Papier/Karton"): 4.70,
    ("750L", "Restafval"): 18.38,
    ("770L", "Restafval"): 18.38,
    ("770L", "Papier/Karton"): 4.70,
    ("1100L", "Restafval"): 23.63,
    ("1600L", "Restafval"): 33.83,
    ("1700L", "Restafval"): 33.83,
    ("1100L", "Papier/Karton"): 4.70,
    ("1600L", "Papier/Karton"): 4.70,
    ("1700L", "Papier/Karton"): 4.70,
    ("2400L", "Papier/Karton"): 4.70,
    ("-", "Papier/Karton"): 55.00,
}

DEFAULT_GIANLUCA_LOCS = pd.DataFrame([
    {"locatienummer": "473810001", "handelingskosten": 15.61},
    {"locatienummer": "2009100001", "handelingskosten": 15.61},
    {"locatienummer": "424980001", "handelingskosten": 15.61},
    {"locatienummer": "590930002", "handelingskosten": 15.61},
    {"locatienummer": "339960001", "handelingskosten": 15.61},
    {"locatienummer": "505660001", "handelingskosten": 15.61},
    {"locatienummer": "603760001", "handelingskosten": 15.61},
    {"locatienummer": "620640001", "handelingskosten": 15.61},
    {"locatienummer": "612540001", "handelingskosten": 15.61},
])

# Km-heffing (vrachtwagenheffing) per leverancier, naast de brandstoftoeslag.
#   haakarm_pct      = percentage over het orderbedrag van transportregels
#                      (productomschrijving bevat "Transport")
#   karton_per_stop  = vast bedrag per stop bij een lediging Papier/Karton,
#                      dus niet op transportregels en niet per container
# Leveranciers die hier niet in staan krijgen geen km-heffing:
#   Papierhandel Jansen  - geen km-heffing afgesproken
#   Rowill               - geen afspraken gemaakt
#   Gianluca, Bal Recycling, Meertens - afspraak nog niet bekend
KM_HEFFING = {
    "Van Bruchem":        {"haakarm_pct": 0.04, "karton_per_stop": 0.20},
    "Recycling-Continue": {"haakarm_pct": 0.03, "karton_per_stop": 0.20},
    "Revema":             {"haakarm_pct": 0.00, "karton_per_stop": 0.20},
    "Schuman":            {"haakarm_pct": 0.00, "karton_per_stop": 0.20},
    "Visser Assen":       {"haakarm_pct": 0.00, "karton_per_stop": 0.20},
}

DEFAULT_RULES = {
    "rule_status_zero": True,
    "rule_partner_zero": True,
    "rule_client_msn_minpay": True,
    "rule_dedup_per_stop": True,
    "rule_gianluca_handlingskosten": True,
    "rule_vanbruchem_pers_92": True,
    "rule_vanbruchem_add_kg_row": True,
    "rule_brandstoftoeslag": False,
    "rule_lege_uitgevoerd_nul": False,
    "rule_km_heffing": True,
}

DEFAULT_KEYWORDS = ["balen", "zakken", "afzet", "pers"]

# Van Bruchem pers-afspraken per plaats
VAN_BRUCHEM_PERS_PRICES = {
    "tiel": 106.25,
    "geldermalsen": 85.00
}

# -------------------- HELPERS --------------------
# Kolomnamen zoals ze exact in een MSN-export staan. Wordt gebruikt om de
# echte kopregel te vinden: MSN zet boven de tabel vaak een filterbanner
# ("Toegepaste filters: [Leverancier] is ..."). Zoeken op 'bevat Leverancier'
# pakt dan die banner en de hele inlezing loopt mis.
HEADER_HINTS = {
    "ophaaldatum", "locatienummer", "debiteurnummer", "leverancier", "klantnaam",
    "klanttype", "dienst logistiek", "status", "productomschrijving", "artikelcode",
    "afvalstroom", "gewicht", "straat", "huisnr", "postcode", "plaats",
    "verantwoordelijke partij", "volume", "inzamelmiddel", "ophaaldag",
    "# uitgevoerd", "# gepland", "uitgevoerd", "gepland",
}


def _header_score(cells) -> int:
    """Aantal cellen in een rij dat exact een bekende kolomnaam is."""
    return sum(
        1 for v in cells
        if str(v).strip().replace("\u00A0", " ").lower() in HEADER_HINTS
    )


@st.cache_data(show_spinner=False)
def read_excel(file):
    preview = pd.read_excel(file, nrows=15, header=None)
    scores = preview.apply(lambda r: _header_score(r.tolist()), axis=1)

    # Minstens 3 exacte treffers, anders is het geen kopregel maar losse tekst.
    header_index = int(scores.idxmax()) if scores.max() >= 3 else 0
    df = pd.read_excel(file, header=header_index)

    df.columns = [str(c).strip().replace("\u00A0", " ") for c in df.columns]

    # Lege hulpkolommen en de losse voettekst ("Toegepaste filters: ...") weg.
    df = df.loc[:, [not str(c).startswith("Unnamed") for c in df.columns]]
    df = df.dropna(axis=0, how="all")

    alias_map = {
        "# uitgevoerd": "Uitgevoerd",
        "# gepland": "Gepland",
        "aantal uitgevoerd": "Uitgevoerd",
        "aantal gepland": "Gepland",
        "uitgevoerd aantal": "Uitgevoerd",
        "gepland aantal": "Gepland"
    }
    new_cols = []
    for c in df.columns:
        key = str(c).strip().lower()
        new_cols.append(alias_map.get(key, str(c).strip()))
    df.columns = new_cols
    return df


def get_col(df, hint):
    for c in df.columns:
        if hint.lower() in str(c).lower():
            return c
    return None


def supplier_rows_mask(df: pd.DataFrame, supplier_col: str, supplier_name: str):
    """Rijen van één leverancier. regex=False, anders worden '.' en '(' in een
    leveranciersnaam als regex uitgelegd."""
    zoek = SUPPLIER_MATCH.get(supplier_name, supplier_name).lower()
    return df[supplier_col].astype(str).str.lower().str.contains(zoek, regex=False, na=False)


def stable_key(s) -> str:
    """Stabiele sleutel voor Streamlit-widgets. hash() van een string wisselt
    per Python-proces, waardoor toggle-standen na een herstart verspringen."""
    return hashlib.md5(str(s).encode("utf-8")).hexdigest()[:12]


# Map met tarievenexports uit MSN ("Tarieven <leverancier>.xlsx").
# Puur ter controle: de app rekent met de tarieven uit de tarievenkaart hierboven.
# Deze lijst laat zien welke producten de leverancier officieel voert, zodat
# nieuwe of gewijzigde productomschrijvingen opvallen.
TARIEVEN_DIR = Path(__file__).resolve().parent.parent / "data" / "tarieven"


@st.cache_data(show_spinner=False)
def load_tarieflijst(bron) -> pd.DataFrame:
    """Leest een MSN-tarievenexport. Geeft een lege DataFrame bij problemen."""
    try:
        df = pd.read_excel(bron)
    except Exception:
        return pd.DataFrame()

    df.columns = [str(c).strip() for c in df.columns]
    kolommen = ["Leverancier", "Productomschrijving", "Basistarief", "Afvalstroom", "Inzamelmiddel"]
    aanwezig = [c for c in kolommen if c in df.columns]
    if "Productomschrijving" not in aanwezig:
        return pd.DataFrame()

    df = df[aanwezig].copy()
    df = df[df["Productomschrijving"].notna()]
    df["Productomschrijving"] = df["Productomschrijving"].astype(str).str.strip()
    return df.reset_index(drop=True)


def tarieflijst_voor(supplier_name: str) -> pd.DataFrame:
    """Zoekt in data/tarieven naar de export van deze leverancier."""
    if not TARIEVEN_DIR.is_dir():
        return pd.DataFrame()

    zoek = SUPPLIER_MATCH.get(supplier_name, supplier_name).lower()
    for pad in sorted(TARIEVEN_DIR.glob("*.xls*")):
        if zoek in pad.stem.lower():
            return load_tarieflijst(str(pad))
    return pd.DataFrame()


def normalize_afvalstroom(v):
    v = str(v).strip().lower().replace(" ", "")
    if "papier" in v and "karton" in v:
        return "Papier/Karton"
    if "rest" in v:
        return "Restafval"
    if "vertrouw" in v:
        return "Vertrouwelijk papier"
    return v


def normalize_volume(v):
    v = str(v).strip().upper().replace(" ", "")
    if v.isdigit() and not v.endswith("L"):
        v += "L"
    return v


def normalize_volume_any(v):
    s = str(v).strip().upper().replace(" ", "")
    if s.isdigit():
        return s + "L"
    return s.replace("M³", "M3")


def normalize_loc(l):
    if l is None:
        return ""
    s = str(l).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def stop_key(row):
    """Sleutel voor 'een stop': ophaaldag + locatienummer."""
    loc_key = normalize_loc(row.get("Locatienummer", ""))
    ophaal_raw = row.get("Ophaaldatum", None)
    ophaal_dt = pd.to_datetime(ophaal_raw, errors="coerce")
    dag_key = ophaal_dt.date().isoformat() if pd.notna(ophaal_dt) else str(ophaal_raw).strip()
    return (dag_key, loc_key)


def units_from_row(row, tarieftype, lege_uitgevoerd_nul: bool = False):
    n = pd.to_numeric(row.get("Uitgevoerd", None), errors="coerce")

    if pd.isna(n):
        # Geen (leesbaar) aantal ingevuld. Standaard blijft het historische
        # gedrag: er ligt een order, dus tel 1 eenheid. Zet de regel
        # 'lege_uitgevoerd_nul' aan om zulke regels op 0 te zetten.
        return 0 if lege_uitgevoerd_nul else 1

    return max(int(n), 0) if tarieftype == "per_kiep" else (1 if n > 0 else 0)


def match_price(row, pricing_df, supplier):
    afst = str(row.get("Afvalstroom", "")).strip()
    zoek = SUPPLIER_MATCH.get(supplier, supplier).lower()
    df = pricing_df[
        pricing_df["leverancier"].astype(str).str.lower().str.contains(zoek, regex=False, na=False)
    ]

    # Tarief per afvalstroom gaat voor op het algemene tarief van de leverancier.
    for _, r in df.iterrows():
        afst_regel = str(r.get("afvalstroom", "")).strip()
        if afst_regel and afst_regel.lower() == afst.lower():
            return {"tarieftype": r["tarieftype"], "prijs": float(r["prijs"])}

    # Anders de eerste regel zonder afvalstroom (het algemene tarief).
    algemeen = df[df["afvalstroom"].astype(str).str.strip() == ""]
    if not algemeen.empty:
        r = algemeen.iloc[0]
        return {"tarieftype": r["tarieftype"], "prijs": float(r["prijs"])}

    if not df.empty:
        r = df.iloc[0]
        return {"tarieftype": r["tarieftype"], "prijs": float(r["prijs"])}

    return {"tarieftype": "per_stop", "prijs": 0.0}


def get_kg_value(row, df):
    candidates = []
    for c in df.columns:
        cl = str(c).lower().strip()
        if "gewicht" in cl or cl == "kg" or "kilo" in cl:
            candidates.append(c)
    for c in candidates:
        v = row.get(c, None)
        if pd.notna(v) and str(v).strip() != "":
            return v
    return None


def export_excel_bytes(out_df: pd.DataFrame) -> bytes:
    out_export = out_df.copy()
    out_export.columns = [c.upper() for c in out_export.columns]

    if "OPHAALDATUM" in out_export.columns:
        out_export["OPHAALDATUM"] = pd.to_datetime(out_export["OPHAALDATUM"], errors="coerce").dt.strftime("%d-%m-%Y")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        out_export.to_excel(writer, index=False, sheet_name="SelfBilling")
        worksheet = writer.sheets["SelfBilling"]

        for idx, col in enumerate(out_export.columns):
            try:
                max_len = min(max(out_export[col].astype(str).map(len).max(), len(col)) + 2, 30)
            except Exception:
                max_len = min(len(col) + 2, 30)
            worksheet.set_column(idx, idx, max_len)

        if "BEDRAG" in out_export.columns:
            last_row = len(out_export) + 2
            bedrag_col = out_export.columns.get_loc("BEDRAG")
            label_col_idx = max(bedrag_col - 1, 0)

            def excel_col(n):
                s = ""
                n += 1
                while n:
                    n, r = divmod(n - 1, 26)
                    s = chr(65 + r) + s
                return s

            label_cell = f"{excel_col(label_col_idx)}{last_row}"
            bedrag_cell = f"{excel_col(bedrag_col)}{last_row}"
            bedrag_range = f"{excel_col(bedrag_col)}2:{excel_col(bedrag_col)}{last_row - 1}"

            worksheet.write(label_cell, "Totaal te ontvangen bedrag")
            worksheet.write_formula(bedrag_cell, f"=SUM({bedrag_range})")

    buf.seek(0)
    return buf.getvalue()


def apply_product_filter(data: pd.DataFrame, product_col: str, allowed_products: set | None) -> pd.DataFrame:
    if allowed_products is None or not product_col:
        return data
    return data[data[product_col].astype(str).isin(allowed_products)].copy()


def calc_brandstoftoeslag(row, bedrag):
    """
    Berekent brandstoftoeslag per order.
    - Papier/Karton: €0,61 per stop, ook als de klant normaal per kiep wordt berekend.
    - Restafval: 2,5% over het orderbedrag.
    - Transportkosten: 7% over het orderbedrag.

    Let op: transport krijgt prioriteit boven afvalstroom, zodat transportkosten niet ook als rest/papier worden gezien.
    """
    afst = normalize_afvalstroom(row.get("Afvalstroom", ""))
    prod = str(row.get("Productomschrijving", "")).lower()

    if "transport" in prod:
        return round(float(bedrag) * 0.07, 2), "Brandstoftoeslag transportkosten 7%"

    if afst == "Papier/Karton":
        return 0.61, "Brandstoftoeslag Papier/Karton per stop"

    if afst == "Restafval":
        return round(float(bedrag) * 0.025, 2), "Brandstoftoeslag Restafval 2,5%"

    return 0.0, ""


def is_transportregel(prod_txt: str) -> bool:
    """Haakarm-/transportrit. Het woord 'haakarm' staat niet in de MSN-export;
    deze ritten heten daar 'Transport perscontainer 23m3' en soortgelijk."""
    return "transport" in str(prod_txt).lower()


def calc_km_heffing(row, bedrag, supplier_name, prod_txt, afst_norm, seen_karton_stops):
    """
    Km-heffing (vrachtwagenheffing) per order, naast de brandstoftoeslag.
    - Transportregels: percentage over het orderbedrag (Van Bruchem 4%,
      Recycling-Continue 3%).
    - Ledigingen Papier/Karton: vast bedrag per stop, dus eenmaal per
      ophaaldag + locatienummer en niet per container.

    Het percentage rekent over het kale orderbedrag, niet over de
    brandstoftoeslag heen, zodat de rekenvolgorde niet uitmaakt.
    """
    afspraak = KM_HEFFING.get(supplier_name)
    if not afspraak:
        return 0.0, ""

    if is_transportregel(prod_txt):
        pct = float(afspraak.get("haakarm_pct", 0.0))
        if pct <= 0:
            return 0.0, ""
        return round(float(bedrag) * pct, 2), f"Km-heffing haakarm {pct * 100:.0f}%"

    per_stop = float(afspraak.get("karton_per_stop", 0.0))
    if per_stop <= 0 or afst_norm != "Papier/Karton":
        return 0.0, ""

    sleutel = stop_key(row)
    if sleutel in seen_karton_stops:
        return 0.0, ""

    seen_karton_stops.add(sleutel)
    return per_stop, "Km-heffing karton lediging per stop"


def process_supplier(
    data_all: pd.DataFrame,
    supplier_name: str,
    pricing_df: pd.DataFrame,
    rules: dict,
    gianluca_exceptions: pd.DataFrame,
    allowed_products: set | None
) -> pd.DataFrame:
    supplier = supplier_name.lower()

    supplier_col = get_col(data_all, "leverancier")
    if not supplier_col:
        return pd.DataFrame()

    data = data_all[supplier_rows_mask(data_all, supplier_col, supplier_name)].copy()
    if data.empty:
        return pd.DataFrame()

    product_col = next((c for c in data.columns if "productomschrijving" in str(c).lower()), None)
    data = apply_product_filter(data, product_col, allowed_products)
    if data.empty:
        return pd.DataFrame()

    # Kolomnamen één keer opzoeken in plaats van per rij.
    vol_col = get_col(data, "volume")
    afst_col = get_col(data, "afvalstroom")
    lege_nul = rules.get("rule_lege_uitgevoerd_nul", False)

    loc_dict = {}
    if supplier == "gianluca" and rules.get("rule_gianluca_handlingskosten", True):
        loc_dict = {
            normalize_loc(r["locatienummer"]): float(r["handelingskosten"])
            for _, r in gianluca_exceptions.iterrows()
            if pd.notna(r.get("locatienummer", None))
        }

    results = []
    seen_per_stop = set()
    seen_karton_stops = set()

    for _, row in data.iterrows():
        prod_txt = str(row.get(product_col, "")) if product_col else ""
        vol_any = normalize_volume_any(row.get(vol_col, "")) if vol_col else ""
        afst_norm = normalize_afvalstroom(row.get(afst_col, "")) if afst_col else ""

        is_vanbruchem_pers_23_pk = (
            supplier == "van bruchem"
            and ("pers" in prod_txt.lower())
            and (vol_any == "23M3")
            and (afst_norm == "Papier/Karton")
        )

        if supplier == "schuman":
            ttype = "per_kiep"
            volume = normalize_volume(row.get(vol_col, "")) if vol_col else ""
            afst = normalize_afvalstroom(row.get(afst_col, "")) if afst_col else ""
            prijs = float(SCHUMAN_PRICES.get((volume, afst), 0.0))
            qty = units_from_row(row, ttype, lege_nul)
            bedrag = prijs * qty

        elif supplier == "gianluca":
            info = match_price(row, pricing_df, supplier_name)
            prijs = float(info["prijs"])
            qty = units_from_row(row, info["tarieftype"], lege_nul)
            bedrag = prijs if qty > 0 else 0.0

            if rules.get("rule_gianluca_handlingskosten", True):
                loc = normalize_loc(row.get("Locatienummer", ""))
                status_txt = str(row.get("Status", "")).strip().lower()
                if status_txt == "voltooid" and loc in loc_dict:
                    bedrag += loc_dict[loc]

        elif supplier == "visser assen":
            info = match_price(row, pricing_df, supplier_name)
            prijs = float(info["prijs"])
            qty = units_from_row(row, info["tarieftype"], lege_nul)
            bedrag = prijs * qty

        elif supplier == "van bruchem":
            info = match_price(row, pricing_df, supplier_name)
            prijs = float(info["prijs"])
            qty = units_from_row(row, info["tarieftype"], lege_nul)
            bedrag = prijs if info["tarieftype"] == "per_stop" and qty > 0 else prijs * qty

            # Pers-prijzen per plaats, alleen bij uitgevoerd.
            plaats_txt = str(row.get("Plaats", "")).strip().lower()
            is_pers = ("pers" in prod_txt.lower())

            if is_pers and qty > 0:
                for plaats_key, pers_prijs in VAN_BRUCHEM_PERS_PRICES.items():
                    if plaats_key in plaats_txt:
                        prijs = float(pers_prijs)
                        bedrag = float(pers_prijs)
                        break

            # Bestaande afspraak: 23m3 Pers Papier/Karton = €92, alleen als er geen plaats-match was.
            if (
                rules.get("rule_vanbruchem_pers_92", True)
                and is_vanbruchem_pers_23_pk
                and qty > 0
                and not (is_pers and any(k in plaats_txt for k in VAN_BRUCHEM_PERS_PRICES.keys()))
            ):
                prijs = 92.0
                bedrag = 92.0

        else:
            info = match_price(row, pricing_df, supplier_name)
            prijs = float(info["prijs"])
            qty = units_from_row(row, info["tarieftype"], lege_nul)
            bedrag = prijs if info["tarieftype"] == "per_stop" and qty > 0 else prijs * qty

        verantwoordelijke = str(row.get("Verantwoordelijke partij", "")).strip().lower()
        status = str(row.get("Status", "")).strip().lower()

        if rules.get("rule_status_zero", True) and status in ("gepland", "geannuleerd", "discussie"):
            bedrag = 0.0
        elif rules.get("rule_partner_zero", True) and verantwoordelijke == "partner":
            bedrag = 0.0
        elif rules.get("rule_client_msn_minpay", True) and verantwoordelijke in ("client", "msn") and bedrag == 0 and prijs > 0:
            bedrag = prijs

        if rules.get("rule_dedup_per_stop", True) and supplier in PER_STOP_DEDUP_SUPPLIERS:
            sleutel = stop_key(row)

            if bedrag > 0 and prijs > 0 and abs(bedrag - prijs) < 1e-9:
                if sleutel in seen_per_stop:
                    bedrag = 0.0
                else:
                    seen_per_stop.add(sleutel)

        base_row = {
            **{c: row.get(c, None) for c in CANON_COLS if c in data.columns},
            "Kilogram": None,
            "Prijs per stuk": prijs,
            "Bedrag": bedrag
        }
        results.append(base_row)

        # Brandstoftoeslag als extra orderregel direct onder de originele order.
        if rules.get("rule_brandstoftoeslag", False) and bedrag > 0:
            toeslag_bedrag, toeslag_omschrijving = calc_brandstoftoeslag(row=row, bedrag=bedrag)

            if toeslag_bedrag > 0:
                toeslag_row = {
                    **{c: row.get(c, None) for c in CANON_COLS if c in data.columns},
                    "Kilogram": None,
                    "Productomschrijving": toeslag_omschrijving,
                    "Prijs per stuk": toeslag_bedrag,
                    "Bedrag": toeslag_bedrag
                }
                results.append(toeslag_row)

        # Km-heffing als extra orderregel, naast de brandstoftoeslag.
        if rules.get("rule_km_heffing", True) and bedrag > 0:
            km_bedrag, km_omschrijving = calc_km_heffing(
                row=row,
                bedrag=bedrag,
                supplier_name=supplier_name,
                prod_txt=prod_txt,
                afst_norm=afst_norm,
                seen_karton_stops=seen_karton_stops,
            )

            if km_bedrag > 0:
                km_row = {
                    **{c: row.get(c, None) for c in CANON_COLS if c in data.columns},
                    "Kilogram": None,
                    "Productomschrijving": km_omschrijving,
                    "Prijs per stuk": km_bedrag,
                    "Bedrag": km_bedrag
                }
                results.append(km_row)

        if supplier == "van bruchem" and rules.get("rule_vanbruchem_add_kg_row", True) and is_vanbruchem_pers_23_pk:
            kg_row = {
                **{c: row.get(c, None) for c in CANON_COLS if c in data.columns},
                "Kilogram": get_kg_value(row, data),
                "Productomschrijving": "Kilogrammen opgehaald met pers (23m3)",
                "Prijs per stuk": 0.0,
                "Bedrag": 0.0
            }
            results.append(kg_row)

    return pd.DataFrame(results)


def toon_samenvatting(out_df: pd.DataFrame, label: str) -> None:
    """Totaal, aantal regels en nulregels, zodat je niet eerst de Excel hoeft te openen."""
    bedrag = pd.to_numeric(out_df.get("Bedrag"), errors="coerce").fillna(0.0)
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Totaal {label}", f"€ {bedrag.sum():,.2f}".replace(",", "@").replace(".", ",").replace("@", "."))
    c2.metric("Regels", f"{len(out_df)}")
    c3.metric("Regels € 0,00", f"{int((bedrag == 0).sum())}")


# -------------------- UI: MODE --------------------
mode = st.radio(
    "Kies modus:",
    ["1 leverancier", "Alle leveranciers tegelijk (per leverancier Excel)"],
    index=0
)
process_all = (mode != "1 leverancier")

# -------------------- UI: KEYWORDS --------------------
st.subheader("Trefwoorden (voor productomschrijvingen)")
kw_text = st.text_input(
    "Trefwoorden (komma-gescheiden)",
    value=", ".join(DEFAULT_KEYWORDS),
    help="Alleen productomschrijvingen die één van deze woorden bevatten kun je per leverancier aan/uit zetten."
)
KEYWORDS = [k.strip().lower() for k in kw_text.split(",") if k.strip()]

# -------------------- UI: RULES + PRICING --------------------
st.subheader("Instellingen per leverancier")

pricing_by_supplier = {}
rules_by_supplier = {}
gianluca_exceptions = DEFAULT_GIANLUCA_LOCS.copy()


def supplier_pricing_default(s: str) -> pd.DataFrame:
    zoek = SUPPLIER_MATCH.get(s, s).lower()
    return DEFAULT_PRICING_ALL[
        DEFAULT_PRICING_ALL["leverancier"].str.lower().str.contains(zoek, regex=False, na=False)
    ].reset_index(drop=True)


def supplier_rules_editor(s: str, key_prefix: str) -> dict:
    with st.expander(f"Regels: {s}", expanded=False):
        r = DEFAULT_RULES.copy()

        r["rule_status_zero"] = st.checkbox(
            "Status (Gepland/Geannuleerd/Discussie) => bedrag 0",
            value=r["rule_status_zero"],
            key=f"{key_prefix}_status"
        )
        r["rule_partner_zero"] = st.checkbox(
            "Verantwoordelijke partij = Partner => bedrag 0",
            value=r["rule_partner_zero"],
            key=f"{key_prefix}_partner"
        )
        r["rule_client_msn_minpay"] = st.checkbox(
            "Client/MSN: als bedrag 0 maar prijs>0 => alsnog prijs",
            value=r["rule_client_msn_minpay"],
            key=f"{key_prefix}_clientmsn"
        )
        r["rule_dedup_per_stop"] = st.checkbox(
            "Deduplicatie per_stop (zelfde dag + locatienummer => niet 2x stopfee)",
            value=r["rule_dedup_per_stop"],
            key=f"{key_prefix}_dedup"
        )
        r["rule_brandstoftoeslag"] = st.checkbox(
            "Brandstoftoeslag toevoegen per order",
            value=r["rule_brandstoftoeslag"],
            key=f"{key_prefix}_brandstoftoeslag",
            help="Voegt per order een extra Excel-regel toe: Papier/Karton €0,61 per stop, Restafval 2,5%, Transportkosten 7%."
        )
        afspraak = KM_HEFFING.get(s)
        r["rule_km_heffing"] = st.checkbox(
            "Km-heffing toevoegen per order",
            value=r["rule_km_heffing"],
            key=f"{key_prefix}_kmheffing",
            help="Voegt een extra Excel-regel toe met de vrachtwagenheffing, naast de brandstoftoeslag."
        )
        if afspraak:
            regels = []
            if afspraak.get("haakarm_pct", 0):
                regels.append(f"{afspraak['haakarm_pct'] * 100:.0f}% over transport-/haakarmregels")
            if afspraak.get("karton_per_stop", 0):
                bedrag_txt = f"{afspraak['karton_per_stop']:.2f}".replace(".", ",")
                regels.append(f"€ {bedrag_txt} per stop bij lediging Papier/Karton")
            st.caption("Afspraak km-heffing: " + " en ".join(regels) + ".")
        else:
            st.caption("Geen km-heffing afgesproken voor deze leverancier.")

        r["rule_lege_uitgevoerd_nul"] = st.checkbox(
            "Lege kolom 'Uitgevoerd' => 0 eenheden (i.p.v. 1)",
            value=r["rule_lege_uitgevoerd_nul"],
            key=f"{key_prefix}_legeuitgevoerd",
            help=(
                "Staat deze uit, dan telt een order zonder ingevuld aantal als 1 eenheid. "
                "Bij per_kiep-leveranciers wordt zo'n regel dan volledig betaald. "
                "Zet aan om alleen te betalen wat aantoonbaar is uitgevoerd."
            )
        )

        if s.lower() == "gianluca":
            r["rule_gianluca_handlingskosten"] = st.checkbox(
                "Gianluca: handelingskosten op uitzonderingslocaties (alleen bij VOLTOOID)",
                value=r["rule_gianluca_handlingskosten"],
                key=f"{key_prefix}_gianluca_hk"
            )

        if s.lower() == "van bruchem":
            r["rule_vanbruchem_pers_92"] = st.checkbox(
                "Van Bruchem: pers 23m3 Papier/Karton = €92 (alleen bij uitgevoerd)",
                value=r["rule_vanbruchem_pers_92"],
                key=f"{key_prefix}_vb_pers92"
            )
            r["rule_vanbruchem_add_kg_row"] = st.checkbox(
                "Van Bruchem: extra kilogram-regel onder persregel (Bedrag = 0)",
                value=r["rule_vanbruchem_add_kg_row"],
                key=f"{key_prefix}_vb_kgrow"
            )

        return r


if process_all:
    for s in SUPPLIERS:
        with st.expander(f"Tarieven: {s}", expanded=False):
            pricing_by_supplier[s] = st.data_editor(
                supplier_pricing_default(s),
                use_container_width=True,
                num_rows="dynamic",
                key=f"pricing_{s}"
            )
        rules_by_supplier[s] = supplier_rules_editor(s, key_prefix=f"rules_{s}")

        if s.lower() == "schuman":
            with st.expander("Prijstabel Schuman", expanded=False):
                st.dataframe(
                    pd.DataFrame([{"Volume": v[0], "Afvalstroom": v[1], "Prijs (€)": p} for v, p in SCHUMAN_PRICES.items()]),
                    use_container_width=True,
                )

    with st.expander("Gianluca: uitzonderingen / handelingskosten", expanded=False):
        st.markdown("Locatienummers hieronder krijgen handelingskosten (alleen bij status VOLTOOID).")
        gianluca_exceptions = st.data_editor(
            DEFAULT_GIANLUCA_LOCS,
            use_container_width=True,
            num_rows="dynamic",
            key="gianluca_ex_all"
        )

else:
    selected_supplier = st.selectbox("Kies leverancier:", SUPPLIERS)
    st.info(f"Berekening en export gelden alleen voor **{selected_supplier}**.")

    with st.expander("Tarieven (geselecteerde leverancier)", expanded=True):
        pricing_by_supplier[selected_supplier] = st.data_editor(
            supplier_pricing_default(selected_supplier),
            use_container_width=True,
            num_rows="dynamic",
            key="pricing_single"
        )

    rules_by_supplier[selected_supplier] = supplier_rules_editor(selected_supplier, key_prefix="rules_single")

    if selected_supplier.lower() == "schuman":
        with st.expander("Prijstabel Schuman", expanded=False):
            st.dataframe(
                pd.DataFrame([{"Volume": v[0], "Afvalstroom": v[1], "Prijs (€)": p} for v, p in SCHUMAN_PRICES.items()]),
                use_container_width=True,
            )

    if selected_supplier.lower() == "gianluca":
        with st.expander("Gianluca: uitzonderingen / handelingskosten", expanded=False):
            gianluca_exceptions = st.data_editor(
                DEFAULT_GIANLUCA_LOCS,
                use_container_width=True,
                num_rows="dynamic",
                key="gianluca_ex_single"
            )
    else:
        gianluca_exceptions = pd.DataFrame(columns=["locatienummer", "handelingskosten"])

# -------------------- UPLOAD --------------------
st.subheader("Upload leveranciers-Excel(s)")
files = st.file_uploader("Selecteer Excel-bestanden", type=["xlsx", "xls"], accept_multiple_files=True)

if not files:
    st.info("Upload één of meer Excel-bestanden om te berekenen en te exporteren.")
    st.stop()

frames = [read_excel(f) for f in files]
data_all = pd.concat(frames, ignore_index=True)

supplier_col = get_col(data_all, "leverancier")
if not supplier_col:
    st.error("Geen kolom gevonden die ‘Leverancier’ bevat. Controleer je Excel.")
    st.stop()

product_col_all = next((c for c in data_all.columns if "productomschrijving" in str(c).lower()), None)

# -------------------- CONTROLE OP HERKENDE LEVERANCIERS --------------------
gekoppeld = pd.Series(False, index=data_all.index)
for _s in SUPPLIERS:
    gekoppeld |= supplier_rows_mask(data_all, supplier_col, _s)

st.success(f"✅ {len(data_all)} orderregels ingelezen uit {len(files)} bestand(en).")

if (~gekoppeld).any():
    onbekend = (
        data_all.loc[~gekoppeld, supplier_col]
        .astype(str).str.strip().value_counts()
    )
    st.warning(
        f"⚠️ {int((~gekoppeld).sum())} regels horen bij een leverancier die niet in de app staat "
        "en verschijnen dus op geen enkele self-billing."
    )
    with st.expander("Welke leveranciers zijn niet gekoppeld?", expanded=False):
        st.dataframe(
            onbekend.rename_axis("Leverancier").reset_index(name="Aantal regels"),
            use_container_width=True,
        )

# -------------------- PRODUCT FILTERS: PER LEVERANCIER (TOGGLES) --------------------
allowed_products_by_supplier: dict[str, set | None] = {}


def compute_allowed_products_toggles(df_sup: pd.DataFrame, supplier_name: str) -> set | None:
    """
    Build allowlist using toggles for impacted products.
    - unaffected always included
    - impacted included only if toggle is ON
    """
    if product_col_all is None:
        st.info("Geen kolom ‘Productomschrijving’ gevonden. Er wordt niet gefilterd.")
        return None

    products_all = sorted(df_sup[product_col_all].dropna().astype(str).unique().tolist())
    if not products_all:
        st.info("Geen productomschrijvingen gevonden. Er wordt niet gefilterd.")
        return None

    impacted = [p for p in products_all if any(k in p.lower() for k in KEYWORDS)]
    unaffected = [p for p in products_all if p not in impacted]

    st.write(f"🔎 Gevonden **{len(impacted)}** met trefwoord en **{len(unaffected)}** zonder trefwoord.")
    st.caption("Alles zonder trefwoord gaat altijd mee. Zet hieronder alleen trefwoord-regels aan/uit.")

    active_impacted = []

    if impacted:
        cols = st.columns(2)
        for i, prod in enumerate(impacted):
            key = f"tgl_{supplier_name}_{stable_key(prod)}"
            with cols[i % 2]:
                if st.toggle(prod, value=True, key=key):
                    active_impacted.append(prod)

    allowed = set(unaffected) | set(active_impacted)

    excluded = set(impacted) - set(active_impacted)
    st.success(f"✅ Meegenomen: {len(allowed)} productomschrijvingen (waarvan {len(active_impacted)} met trefwoord).")
    if excluded:
        st.warning(f"🚫 Uitgesloten (trefwoord): {len(excluded)}")

    toon_tarieflijst_controle(products_all, supplier_name)

    return allowed


def toon_tarieflijst_controle(products_in_orders: list, supplier_name: str) -> None:
    """Vergelijkt de productomschrijvingen in het orderbestand met de officiele
    tarievenexport van de leverancier, als die beschikbaar is."""
    tarieven = tarieflijst_voor(supplier_name)

    upload = st.file_uploader(
        f"Tarievenexport {supplier_name} (optioneel, ter controle)",
        type=["xlsx", "xls"],
        key=f"tarieven_{stable_key(supplier_name)}",
        help="Export uit MSN: 'Tarieven <leverancier>.xlsx'. Overschrijft het bestand uit data/tarieven.",
    )
    if upload is not None:
        tarieven = load_tarieflijst(upload)

    if tarieven.empty:
        return

    bekend = set(tarieven["Productomschrijving"].str.strip())
    onbekend = sorted(p for p in products_in_orders if str(p).strip() not in bekend)

    with st.expander(f"📋 Tarieflijst {supplier_name} ({len(bekend)} producten)", expanded=False):
        if onbekend:
            st.warning(
                f"⚠️ {len(onbekend)} productomschrijving(en) in het orderbestand staan niet "
                "in de tarievenlijst. Controleer of het tarief nog klopt."
            )
            st.dataframe(
                pd.DataFrame({"Niet in tarievenlijst": onbekend}),
                use_container_width=True,
            )
        else:
            st.success("✅ Alle productomschrijvingen komen voor in de tarievenlijst.")

        st.dataframe(tarieven, use_container_width=True)


if process_all:
    st.subheader("🧩 Productomschrijvingen per leverancier (bulk)")
    st.caption("Per leverancier kun je alleen de productomschrijvingen mét trefwoord aan/uit zetten.")

    present_suppliers = [
        s for s in SUPPLIERS
        if supplier_rows_mask(data_all, supplier_col, s).any()
    ]
    if not present_suppliers:
        st.warning("Geen bekende leveranciers gevonden in dit bestand.")
        st.stop()

    for s in present_suppliers:
        df_sup = data_all[supplier_rows_mask(data_all, supplier_col, s)].copy()
        with st.expander(f"Productomschrijvingen: {s}", expanded=False):
            allowed_products_by_supplier[s] = compute_allowed_products_toggles(df_sup, supplier_name=s)

else:
    st.subheader("🧩 Productomschrijvingen (geselecteerde leverancier)")
    df_sup = data_all[supplier_rows_mask(data_all, supplier_col, selected_supplier)].copy()
    allowed_products_by_supplier[selected_supplier] = compute_allowed_products_toggles(df_sup, supplier_name=selected_supplier)

# -------------------- RUN --------------------
if process_all:
    st.subheader("Resultaten per leverancier")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for s in present_suppliers:
            out_df = process_supplier(
                data_all=data_all,
                supplier_name=s,
                pricing_df=pricing_by_supplier.get(s, supplier_pricing_default(s)),
                rules=rules_by_supplier.get(s, DEFAULT_RULES),
                gianluca_exceptions=(
                    gianluca_exceptions
                    if s.lower() == "gianluca"
                    else pd.DataFrame(columns=["locatienummer", "handelingskosten"])
                ),
                allowed_products=allowed_products_by_supplier.get(s, None)
            )

            if out_df.empty:
                st.markdown(f"**{s}** — geen regels na filtering.")
                continue

            st.markdown(f"**{s}**")
            toon_samenvatting(out_df, s)
            st.dataframe(out_df.head(20), use_container_width=True)

            xbytes = export_excel_bytes(out_df)
            fname = f"selfbilling_{s.lower().replace(' ', '_')}.xlsx"
            zf.writestr(fname, xbytes)

    zip_buf.seek(0)
    st.download_button(
        label="💾 Download alle self-billings (ZIP)",
        data=zip_buf.getvalue(),
        file_name="selfbilling_per_leverancier.zip",
        mime="application/zip"
    )

else:
    out_df = process_supplier(
        data_all=data_all,
        supplier_name=selected_supplier,
        pricing_df=pricing_by_supplier[selected_supplier],
        rules=rules_by_supplier[selected_supplier],
        gianluca_exceptions=(
            gianluca_exceptions
            if selected_supplier.lower() == "gianluca"
            else pd.DataFrame(columns=["locatienummer", "handelingskosten"])
        ),
        allowed_products=allowed_products_by_supplier.get(selected_supplier, None)
    )

    st.subheader("Bekijk en exporteer resultaat")

    if out_df.empty:
        st.warning("Geen regels voor deze leverancier na filtering.")
        st.stop()

    toon_samenvatting(out_df, selected_supplier)
    st.dataframe(out_df.head(40), use_container_width=True)

    xbytes = export_excel_bytes(out_df)
    st.download_button(
        label=f"💾 Download self-billing ({selected_supplier}).xlsx",
        data=xbytes,
        file_name=f"selfbilling_{selected_supplier.lower().replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
