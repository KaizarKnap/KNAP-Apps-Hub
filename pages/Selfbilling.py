import io
import zipfile
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

DEFAULT_RULES = {
    # algemene “na-berekening” logica
    "rule_status_zero": True,          # gepland/geannuleerd/discussie => 0
    "rule_partner_zero": True,         # verantwoordelijke = partner => 0
    "rule_client_msn_minpay": True,    # client/msn en bedrag=0 maar prijs>0 => prijs

    # dedup per_stop leveranciers
    "rule_dedup_per_stop": True,

    # supplier-specific
    "rule_gianluca_handlingskosten": True,
    "rule_vanbruchem_pers_92": True,
    "rule_vanbruchem_add_kg_row": True,
}

# -------------------- HELPERS --------------------
@st.cache_data(show_spinner=False)
def read_excel(file):
    preview = pd.read_excel(file, nrows=10, header=None)
    header_row = preview.apply(
        lambda r: r.astype(str).str.contains("Leverancier|Afvalstroom", case=False, na=False)
    ).any(axis=1)
    header_index = header_row.idxmax() if header_row.any() else 0
    df = pd.read_excel(file, header=header_index)

    df.columns = [str(c).strip().replace("\u00A0", " ") for c in df.columns]

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
            if str(r.get("afvalstroom", "")).lower() == str(afst).lower():
                return {"tarieftype": "per_kiep", "prijs": float(r["prijs"])}

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

        # totaalregel
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
            bedrag_range = f"{excel_col(bedrag_col)}2:{excel_col(bedrag_col)}{last_row-1}"

            worksheet.write(label_cell, "Totaal te ontvangen bedrag")
            worksheet.write_array_formula(f"{bedrag_cell}:{bedrag_cell}", f"=SOM({bedrag_range})")

    buf.seek(0)
    return buf.getvalue()

def process_supplier(
    data_all: pd.DataFrame,
    supplier_name: str,
    pricing_df: pd.DataFrame,
    rules: dict,
    gianluca_exceptions: pd.DataFrame
) -> pd.DataFrame:
    supplier = supplier_name.lower()

    supplier_col = get_col(data_all, "leverancier")
    if not supplier_col:
        return pd.DataFrame()

    data = data_all[data_all[supplier_col].astype(str).str.lower().str.contains(supplier)].copy()
    if data.empty:
        return pd.DataFrame()

    # exceptions dict voor Gianluca
    loc_dict = {}
    if supplier == "gianluca" and rules.get("rule_gianluca_handlingskosten", True):
        loc_dict = {
            normalize_loc(r["locatienummer"]): float(r["handelingskosten"])
            for _, r in gianluca_exceptions.iterrows()
            if pd.notna(r.get("locatienummer", None))
        }

    results = []
    seen_per_stop = set()

    for _, row in data.iterrows():
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

        # ---------- prijsberekening ----------
        if supplier == "schuman":
            ttype = "per_kiep"
            volume = normalize_volume(row.get(vol_col, "")) if vol_col else ""
            afst = normalize_afvalstroom(row.get(afst_col, "")) if afst_col else ""
            prijs = float(SCHUMAN_PRICES.get((volume, afst), 0.0))
            qty = units_from_row(row, ttype)
            bedrag = prijs * qty

        elif supplier == "gianluca":
            info = match_price(row, pricing_df, supplier_name)
            prijs = float(info["prijs"])
            qty = units_from_row(row, info["tarieftype"])
            bedrag = prijs if qty > 0 else 0.0

            if rules.get("rule_gianluca_handlingskosten", True):
                loc = normalize_loc(row.get("Locatienummer", ""))
                status_txt = str(row.get("Status", "")).strip().lower()
                if status_txt == "voltooid" and loc in loc_dict:
                    bedrag += loc_dict[loc]

        elif supplier == "visser assen":
            info = match_price(row, pricing_df, supplier_name)
            prijs = float(info["prijs"])
            qty = units_from_row(row, info["tarieftype"])
            bedrag = prijs * qty

        elif supplier == "van bruchem":
            info = match_price(row, pricing_df, supplier_name)
            prijs = float(info["prijs"])
            qty = units_from_row(row, info["tarieftype"])
            bedrag = prijs if info["tarieftype"] == "per_stop" and qty > 0 else prijs * qty

            # Pers 23m3 Papier/Karton: €92 ALS uitgevoerd (aan/uit)
            if rules.get("rule_vanbruchem_pers_92", True) and is_vanbruchem_pers_23_pk and qty > 0:
                prijs = 92.0
                bedrag = 92.0

        else:
            info = match_price(row, pricing_df, supplier_name)
            prijs = float(info["prijs"])
            qty = units_from_row(row, info["tarieftype"])
            bedrag = prijs if info["tarieftype"] == "per_stop" and qty > 0 else prijs * qty

        # ---------- status/verantwoordelijke regels ----------
        verantwoordelijke = str(row.get("Verantwoordelijke partij", "")).strip().lower()
        status = str(row.get("Status", "")).strip().lower()

        if rules.get("rule_status_zero", True) and status in ("gepland", "geannuleerd", "discussie"):
            bedrag = 0.0
        elif rules.get("rule_partner_zero", True) and verantwoordelijke == "partner":
            bedrag = 0.0
        elif rules.get("rule_client_msn_minpay", True) and verantwoordelijke in ("client", "msn") and bedrag == 0 and prijs > 0:
            bedrag = prijs

        # ---------- dedup per_stop ----------
        if rules.get("rule_dedup_per_stop", True) and supplier in ("recycling-continue", "gianluca", "revema", "gogogo"):
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

        # ---------- base row (Kilogram altijd leeg) ----------
        base_row = {
            **{c: row.get(c, None) for c in CANON_COLS if c in data.columns},
            "Kilogram": None,
            "Prijs per stuk": prijs,
            "Bedrag": bedrag
        }
        results.append(base_row)

        # ---------- extra kilogram-regel onder persregel (aan/uit) ----------
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

# -------------------- UI: MODE --------------------
mode = st.radio(
    "Kies modus:",
    ["1 leverancier", "Alle leveranciers tegelijk (per leverancier Excel)"],
    index=0
)
process_all = (mode != "1 leverancier")

# -------------------- UI: RULES + PRICING --------------------
st.subheader("Instellingen per leverancier")

pricing_by_supplier = {}
rules_by_supplier = {}
gianluca_exceptions = DEFAULT_GIANLUCA_LOCS.copy()

def supplier_pricing_default(s: str) -> pd.DataFrame:
    return DEFAULT_PRICING_ALL[DEFAULT_PRICING_ALL["leverancier"].str.lower().str.contains(s.lower())].reset_index(drop=True)

def supplier_rules_editor(s: str, key_prefix: str) -> dict:
    with st.expander(f"Regels: {s}", expanded=False):
        r = DEFAULT_RULES.copy()

        r["rule_status_zero"] = st.checkbox("Status (Gepland/Geannuleerd/Discussie) => bedrag 0", value=r["rule_status_zero"], key=f"{key_prefix}_status")
        r["rule_partner_zero"] = st.checkbox("Verantwoordelijke partij = Partner => bedrag 0", value=r["rule_partner_zero"], key=f"{key_prefix}_partner")
        r["rule_client_msn_minpay"] = st.checkbox("Client/MSN: als bedrag 0 maar prijs>0 => alsnog prijs", value=r["rule_client_msn_minpay"], key=f"{key_prefix}_clientmsn")
        r["rule_dedup_per_stop"] = st.checkbox("Deduplicatie per_stop (zelfde dag + locatienummer => niet 2x stopfee)", value=r["rule_dedup_per_stop"], key=f"{key_prefix}_dedup")

        if s.lower() == "gianluca":
            r["rule_gianluca_handlingskosten"] = st.checkbox("Gianluca: handelingskosten op uitzonderingslocaties (alleen bij VOLTOOID)", value=r["rule_gianluca_handlingskosten"], key=f"{key_prefix}_gianluca_hk")

        if s.lower() == "van bruchem":
            r["rule_vanbruchem_pers_92"] = st.checkbox("Van Bruchem: pers 23m3 Papier/Karton = €92 (alleen bij uitgevoerd)", value=r["rule_vanbruchem_pers_92"], key=f"{key_prefix}_vb_pers92")
            r["rule_vanbruchem_add_kg_row"] = st.checkbox("Van Bruchem: extra kilogram-regel onder persregel (Bedrag = 0)", value=r["rule_vanbruchem_add_kg_row"], key=f"{key_prefix}_vb_kgrow")

        return r

if process_all:
    # Per leverancier: tarieven + regels
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
            DEFAULT_GIANLUCA_LOCS, use_container_width=True, num_rows="dynamic", key="gianluca_ex_all"
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
                DEFAULT_GIANLUCA_LOCS, use_container_width=True, num_rows="dynamic", key="gianluca_ex_single"
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

# -------------------- PRODUCTOMSCHRIJVING FILTER (globaal) --------------------
st.subheader("🧩 Productomschrijvingen")
st.caption("Alle regels gaan standaard mee. Alleen productomschrijvingen met trefwoord kun je hieronder (de)activeren.")

product_col = next((c for c in data_all.columns if "productomschrijving" in str(c).lower()), None)
products_all = sorted(data_all[product_col].dropna().astype(str).unique().tolist()) if product_col else []
keywords = ["balen", "zakken", "afzet", "pers"]

if not product_col or not products_all:
    st.info("Geen kolom ‘Productomschrijving’ gevonden of geen waarden. Alles wordt meegenomen.")
    data_filtered = data_all
else:
    impacted = [p for p in products_all if any(k in p.lower() for k in keywords)]
    unaffected = [p for p in products_all if p not in impacted]

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
    data_filtered = data_all[data_all[product_col].astype(str).isin(active_products)].copy()

    excluded = set(impacted) - set(active_impacted)
    st.success(f"✅ Meegenomen: {len(active_products)} productomschrijvingen (waarvan {len(active_impacted)} met trefwoord).")
    if excluded:
        st.warning(f"🚫 Uitgesloten (trefwoord): {len(excluded)}")

# -------------------- RUN --------------------
if process_all:
    present_suppliers = [s for s in SUPPLIERS if data_filtered[supplier_col].astype(str).str.lower().str.contains(s.lower()).any()]
    if not present_suppliers:
        st.warning("Geen bekende leveranciers gevonden in dit bestand.")
        st.stop()

    st.subheader("Resultaten per leverancier")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for s in present_suppliers:
            out_df = process_supplier(
                data_all=data_filtered,
                supplier_name=s,
                pricing_df=pricing_by_supplier.get(s, supplier_pricing_default(s)),
                rules=rules_by_supplier.get(s, DEFAULT_RULES),
                gianluca_exceptions=gianluca_exceptions if s.lower() == "gianluca" else pd.DataFrame(columns=["locatienummer", "handelingskosten"])
            )
            if out_df.empty:
                continue

            st.markdown(f"**{s}** — {len(out_df)} regels")
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
    selected_supplier = selected_supplier  # uit UI
    out_df = process_supplier(
        data_all=data_filtered,
        supplier_name=selected_supplier,
        pricing_df=pricing_by_supplier[selected_supplier],
        rules=rules_by_supplier[selected_supplier],
        gianluca_exceptions=gianluca_exceptions if selected_supplier.lower() == "gianluca" else pd.DataFrame(columns=["locatienummer", "handelingskosten"])
    )

    st.subheader("Bekijk en exporteer resultaat")
    st.dataframe(out_df.head(40), use_container_width=True)

    xbytes = export_excel_bytes(out_df)
    st.download_button(
        label=f"💾 Download self-billing ({selected_supplier}).xlsx",
        data=xbytes,
        file_name=f"selfbilling_{selected_supplier.lower().replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
