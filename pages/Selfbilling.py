import io
import pandas as pd
import streamlit as st

# GEEN st.set_page_config hier (dat gebeurt in Home.py)
st.title("🧾 Self-billing per leverancier")
st.caption("Upload leveranciers-Excel(s), bereken automatisch de self-billing en exporteer het resultaat.")


# Canonieke kolommen (met Kilogram naast Gepland)
CANON_COLS = [
    "Ophaaldatum", "Locatienummer", "Debiteurnummer", "Klantnaam",
    "Leverancier", "Dienst logistiek", "Uitgevoerd", "Gepland",
    "Kilogram",
    "Status", "Productomschrijving", "Afvalstroom", "Straat",
    "Huisnr", "Postcode", "Plaats", "Verantwoordelijke partij"
]

# Standaard tarieven per leverancier
DEFAULT_PRICING_ALL = pd.DataFrame([
    {"leverancier": "Recycling-Continue", "tarieftype": "per_stop", "prijs": 4.00, "afvalstroom": ""},
    {"leverancier": "Gianluca",            "tarieftype": "per_stop", "prijs": 4.15, "afvalstroom": ""},
    {"leverancier": "Revema",              "tarieftype": "per_stop", "prijs": 4.00, "afvalstroom": ""},
    {"leverancier": "Gogogo",              "tarieftype": "per_stop", "prijs": 3.00, "afvalstroom": ""},
    {"leverancier": "Papierhandel Jansen", "tarieftype": "per_kiep", "prijs": 3.50, "afvalstroom": ""},
    {"leverancier": "Visser Assen",        "tarieftype": "per_kiep", "prijs": 4.00,  "afvalstroom": "Papier/Karton"},
    {"leverancier": "Visser Assen",        "tarieftype": "per_kiep", "prijs": 12.50, "afvalstroom": "Vertrouwelijk papier"},
    {"leverancier": "Schuman",             "tarieftype": "per_kiep", "prijs": 0.00,  "afvalstroom": ""},
    {"leverancier": "Van Bruchem",         "tarieftype": "per_kiep", "prijs": 4.00,  "afvalstroom": ""}
])

SUPPLIERS = [
    "Recycling-Continue", "Gianluca", "Revema", "Gogogo",
    "Papierhandel Jansen", "Visser Assen", "Schuman", "Van Bruchem"
]

# Schuman prijs-matrix (Volume, Afvalstroom)
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
    ("1100L", "Papier/Karton"): 4.70,
    ("1600L", "Papier/Karton"): 4.70,
    ("1700L", "Papier/Karton"): 4.70,
    ("2400L", "Papier/Karton"): 4.70,
    ("-", "Papier/Karton"): 55.00,
}


# Helperfuncties
@st.cache_data(show_spinner=False)
def read_excel(file):
    """Leest Excel in, detecteert header en normaliseert kolomnamen."""
    preview = pd.read_excel(file, nrows=10, header=None)
    header_row = preview.apply(
        lambda r: r.astype(str).str.contains("Leverancier|Afvalstroom", case=False, na=False)
    ).any(axis=1)
    header_index = header_row.idxmax() if header_row.any() else 0
    df = pd.read_excel(file, header=header_index)

    # Normaliseer kolomnamen
    df.columns = [str(c).strip().replace("\u00A0", " ") for c in df.columns]

    # Kolom-aliases
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
        key = c.strip().lower()
        new_cols.append(alias_map.get(key, c.strip()))
    df.columns = new_cols

    return df


def get_col(df, hint):
    for c in df.columns:
        if hint.lower() in str(c).lower():
            return c
    return None


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


# ✅ NIEUW: ook m3 varianten normaliseren (voor pers 23m3)
def normalize_volume_any(v):
    """
    Normaliseert zowel L (vaten) als m3 (pers/containers) naar vaste notatie.
    Voorbeeld: '23m3' -> '23M3', '1100' -> '1100L'
    """
    s = str(v).strip().upper().replace(" ", "")
    if s.isdigit():
        return s + "L"
    s = s.replace("M³", "M3")
    return s


def units_from_row(row, tarieftype):
    val = row.get("Uitgevoerd", 0)
    if tarieftype == "per_kiep":
        try:
            return int(val)
        except Exception:
            return 1 if str(val).strip() else 0
    return 1 if str(val).strip() else 0


def match_price(row, pricing_df, supplier):
    afst = str(row.get("Afvalstroom", "")).strip()
    df = pricing_df[pricing_df["leverancier"].str.lower().str.contains(supplier.lower())]

    if supplier.lower() == "visser assen":
        for _, r in df.iterrows():
            if str(r["afvalstroom"]).lower() == str(afst).lower():
                return {"tarieftype": "per_kiep", "prijs": r["prijs"]}

    if not df.empty:
        r = df.iloc[0]
        return {"tarieftype": r["tarieftype"], "prijs": r["prijs"]}

    return {"tarieftype": "per_stop", "prijs": 0.0}


def normalize_loc(l):
    """Zorgt dat locatienummers altijd uniform zijn, ongeacht type of notatie."""
    if l is None:
        return ""
    s = str(l).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def get_kg_value(row, df):
    """
    Probeert een gewicht/kg kolom te vinden en geeft de waarde terug.
    """
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


# UI
selected_supplier = st.selectbox("Kies leverancier:", SUPPLIERS)
st.info(f"Berekening en export gelden alleen voor **{selected_supplier}**.")

# Tarieven + Schuman-tabel
st.subheader("Tarieven voor geselecteerde leverancier")
view = DEFAULT_PRICING_ALL[
    DEFAULT_PRICING_ALL["leverancier"].str.lower().str.contains(selected_supplier.lower())
].reset_index(drop=True)
pricing_editor = st.data_editor(view, use_container_width=True, num_rows="dynamic", key="pricing_editor")

if selected_supplier.lower() == "schuman":
    st.markdown("Prijstabel Schuman")
    st.dataframe(
        pd.DataFrame(
            [{"Volume": v[0], "Afvalstroom": v[1], "Prijs (€)": p} for v, p in SCHUMAN_PRICES.items()]
        ),
        use_container_width=True,
    )

# Uitzonderingen (alleen Gianluca)
if selected_supplier.lower() == "gianluca":
    st.subheader("Uitzonderingen / handelingskosten")
    st.markdown("Locatienummers hieronder krijgen standaard €15 handelingskosten.")
    default_locs = pd.DataFrame([
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
    loc_exceptions = st.data_editor(default_locs, use_container_width=True, num_rows="dynamic", key="loc_exceptions_editor")
else:
    loc_exceptions = pd.DataFrame(columns=["locatienummer", "handelingskosten"])

# Upload bestanden en bereken
st.subheader("Upload leveranciers-Excel(s)")
files = st.file_uploader("Selecteer Excel-bestanden", type=["xlsx", "xls"], accept_multiple_files=True)

if files:
    frames = [read_excel(f) for f in files]
    data = pd.concat(frames, ignore_index=True)

    supplier_col = get_col(data, "leverancier")
    mask = data[supplier_col].astype(str).str.lower().str.contains(selected_supplier.lower()) if supplier_col else [True] * len(data)
    data = data[mask].copy()

    # 🧩 Productomschrijvingen – alleen regels met trefwoord beoordelen
    st.subheader("🧩 Productomschrijvingen")
    st.caption("Alle regels gaan standaard mee. Alleen productomschrijvingen met een trefwoord kun je hieronder (de)activeren.")

    product_col = next((c for c in data.columns if "productomschrijving" in str(c).lower()), None)
    products_all = sorted(data[product_col].dropna().astype(str).unique().tolist()) if product_col else []

    keywords = ["balen", "zakken", "afzet", "pers"]  # pas aan naar wens

    impacted = [p for p in products_all if any(k in p.lower() for k in keywords)]
    unaffected = [p for p in products_all if p not in impacted]

    if not product_col or not products_all:
        st.info("Geen kolom ‘Productomschrijving’ gevonden of geen waarden. Alles wordt meegenomen.")
    else:
        st.write(f"🔎 Gevonden **{len(impacted)}** productomschrijvingen met trefwoord en **{len(unaffected)}** zonder trefwoord.")

        active_impacted = []
        if impacted:
            st.markdown("**Beoordeel productomschrijvingen met trefwoord:**")
            cols = st.columns(2)
            for i, prod in enumerate(impacted):
                with cols[i % 2]:
                    if st.toggle(prod, value=True, key=f"kwprod_{i}"):
                        active_impacted.append(prod)

        active_products = set(unaffected) | set(active_impacted)
        data = data[data[product_col].astype(str).isin(active_products)]

        excluded = set(impacted) - set(active_impacted)
        st.success(f"✅ Meegenomen: {len(active_products)} productomschrijvingen "
                   f"(waarvan {len(active_impacted)} met trefwoord).")
        if excluded:
            st.warning(f"🚫 Uitgesloten (trefwoord): {len(excluded)}")

    # Berekening
    results = []
    loc_dict = {
        normalize_loc(r["locatienummer"]): float(r["handelingskosten"])
        for _, r in loc_exceptions.iterrows()
        if pd.notna(r["locatienummer"])
    }

    seen_per_stop = set()

    for _, row in data.iterrows():
        supplier = selected_supplier.lower()

        # Voor pers-detectie (Van Bruchem)
        product_col_local = next((c for c in data.columns if "productomschrijving" in str(c).lower()), None)
        prod_txt = str(row.get(product_col_local, "")) if product_col_local else ""
        vol_col = get_col(data, "volume")
        afst_col = get_col(data, "afvalstroom")
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
            prijs = SCHUMAN_PRICES.get((volume, afst), 0.0)
            qty = units_from_row(row, ttype)
            bedrag = prijs * qty

        elif supplier == "gianluca":
            info = match_price(row, pricing_editor, selected_supplier)
            prijs = info["prijs"]
            qty = units_from_row(row, info["tarieftype"])
            bedrag = prijs if qty > 0 else 0.0

            loc = normalize_loc(row.get("Locatienummer", ""))
            status = str(row.get("Status", "")).strip().lower()

            if status == "voltooid" and loc in loc_dict:
                bedrag += loc_dict[loc]

        elif supplier == "visser assen":
            info = match_price(row, pricing_editor, selected_supplier)
            prijs = info["prijs"]
            qty = units_from_row(row, info["tarieftype"])
            bedrag = prijs * qty

        elif supplier == "van bruchem":
            info = match_price(row, pricing_editor, selected_supplier)
            prijs = info["prijs"]
            qty = units_from_row(row, info["tarieftype"])
            bedrag = prijs if info["tarieftype"] == "per_stop" and qty > 0 else prijs * qty

            # Pers 23m3 Papier/Karton: €92 ALS uitgevoerd
            if is_vanbruchem_pers_23_pk and qty > 0:
                prijs = 92.0
                bedrag = 92.0

        else:
            info = match_price(row, pricing_editor, selected_supplier)
            prijs = info["prijs"]
            qty = units_from_row(row, info["tarieftype"])
            bedrag = prijs if info["tarieftype"] == "per_stop" and qty > 0 else prijs * qty

        # Verantwoordelijke partij / status logica
        verantwoordelijke = str(row.get("Verantwoordelijke partij", "")).strip().lower()
        status = str(row.get("Status", "")).strip().lower()

        if status in ("gepland", "geannuleerd", "discussie"):
            bedrag = 0.0
        elif verantwoordelijke == "partner":
            bedrag = 0.0
        elif verantwoordelijke in ("client", "msn") and bedrag == 0 and prijs > 0:
            bedrag = prijs

        # Deduplicatie voor per_stop leveranciers
        if supplier in ("recycling-continue", "gianluca", "revema", "gogogo"):
            loc_key = normalize_loc(row.get("Locatienummer", ""))

            ophaal_raw = row.get("Ophaaldatum", None)
            ophaal_dt = pd.to_datetime(ophaal_raw, errors="coerce")
            dag_key = ophaal_dt.date().isoformat() if pd.notna(ophaal_dt) else str(ophaal_raw).strip()

            stop_key = (dag_key, loc_key)

            if bedrag > 0 and prijs > 0 and abs(bedrag - prijs) < 1e-9:
                if stop_key in seen_per_stop:
                    bedrag = 0.0
                else:
                    seen_per_stop.add(stop_key)

        # ✅ Outputregel (Kilogram altijd LEEG op normale regels, inclusief persregel)
        base_row = {
            **{c: row.get(c, None) for c in CANON_COLS if c in data.columns},
            "Kilogram": None,
            "Prijs per stuk": prijs,
            "Bedrag": bedrag
        }
        results.append(base_row)

        # ✅ EXTRA: Kilogram-regel direct onder persregel (hier komt Kilogram WÉL gevuld)
        if is_vanbruchem_pers_23_pk:
            kg_row = {
                **{c: row.get(c, None) for c in CANON_COLS if c in data.columns},
                "Kilogram": get_kg_value(row, data),
                "Productomschrijving": "Kilogrammen opgehaald met pers (23m3)",
                "Prijs per stuk": 0.0,
                "Bedrag": 0.0
            }
            results.append(kg_row)

    out = pd.DataFrame(results)

    # Export
    st.subheader("Bekijk en exporteer resultaat")
    st.dataframe(out.head(40), use_container_width=True)

    out_export = out.copy()
    out_export.columns = [c.upper() for c in out_export.columns]

    if "OPHAALDATUM" in out_export.columns:
        out_export["OPHAALDATUM"] = pd.to_datetime(out_export["OPHAALDATUM"], errors="coerce").dt.strftime("%d-%m-%Y")

    # Exporteer naar Excel met opmaak
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        out_export.to_excel(writer, index=False, sheet_name="SelfBilling")

        workbook = writer.book
        worksheet = writer.sheets["SelfBilling"]

        # Kolombreedte automatisch aanpassen
        for idx, col in enumerate(out_export.columns):
            max_len = min(max(out_export[col].astype(str).map(len).max(), len(col)) + 2, 30)
            worksheet.set_column(idx, idx, max_len)

        # Totaalregel
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
        bedrag_range = f"{excel_col(bedrag_col)}2:{excel_col(bedrag_col)}{last_row-1}"

        worksheet.write(label_cell, "Totaal te ontvangen bedrag")
        worksheet.write_array_formula(f"{bedrag_cell}:{bedrag_cell}", f"=SOM({bedrag_range})")

    buf.seek(0)

    st.download_button(
        label=f"💾 Download self-billing ({selected_supplier}).xlsx",
        data=buf,
        file_name=f"selfbilling_{selected_supplier.lower().replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("Upload één of meer Excel-bestanden om te berekenen en te exporteren.")
