import streamlit as st
import pandas as pd
import io
import re
from datetime import timedelta

# GEEN st.set_page_config hier (dat gebeurt in Home.py)
st.title("⚖️ RVKO Gewichten koppelen en controleren")

st.write("""
Deze app koppelt weeggegevens aan je data en vult automatisch de kolom **'Gewicht'** aan.  
Ondersteunt zowel het oude als het nieuwe leveranciersbestand.
""")

# ---------- Helper functies ----------
def extract_volume(text):
    """Zoekt naar volumewaarde in tekst (bijv. '1100L', '1100 ltr.', '1100 liter')."""
    if pd.isna(text):
        return None
    s = str(text).lower()
    m = re.search(r'(\d{2,4})\s*(l|ltr\.?|liter)\b', s)
    return int(m.group(1)) if m else None


def canon_afval(s):
    """Normaliseert afvalstroomteksten."""
    if pd.isna(s):
        return None
    s = str(s).lower()
    if "bedrijfs" in s or "rest" in s:
        return "restafval"
    if "gft" in s:
        return "gft"
    if "papier" in s:
        return "papier"
    return re.sub(r'[^a-z0-9]', '', s)


def norm_text(x):
    """Normaliseert tekst voor matching."""
    if pd.isna(x):
        return None
    s = str(x).strip().lower()
    s = re.sub(r'[^a-z0-9]', '', s)
    return s if s else None


def parse_euro_number(x):
    """
    Zet waarden als:
    '95,'
    '1.100,'
    '12,5'
    '€ 1.234,56'
    om naar float.
    """
    if pd.isna(x):
        return None

    s = str(x).strip()
    if s == "":
        return None

    s = s.replace("€", "").replace(" ", "")

    # Europees formaat:
    # 1.100,  -> 1100.
    # 12,5    -> 12.5
    s = s.replace(".", "")
    s = s.replace(",", ".")

    # Als string eindigt op punt, haal die weg
    if s.endswith("."):
        s = s[:-1]

    try:
        return float(s)
    except:
        return None


def fill_weight(cur, new):
    """Vult gewicht aan als het leeg of nul is."""
    cur_num = pd.to_numeric(cur, errors="coerce")
    if (pd.isna(cur_num) or cur_num == 0) and pd.notna(new):
        return new
    return cur


def pick_col(df, candidates):
    """Kiest de eerste bestaande kolom uit candidates."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def build_loc_keys(df, ref_col=None, name_col=None, addr_col=None, prefix=""):
    """
    Bouwt meerdere locatie-sleutels voor robuust matchen.
    Prioriteit:
    1. referentie
    2. naam
    3. adres
    """
    if ref_col and ref_col in df.columns:
        df[f"{prefix}loc_ref_tmp"] = df[ref_col].apply(norm_text)
    else:
        df[f"{prefix}loc_ref_tmp"] = None

    if name_col and name_col in df.columns:
        df[f"{prefix}loc_name_tmp"] = df[name_col].apply(norm_text)
    else:
        df[f"{prefix}loc_name_tmp"] = None

    if addr_col and addr_col in df.columns:
        df[f"{prefix}loc_addr_tmp"] = df[addr_col].apply(norm_text)
    else:
        df[f"{prefix}loc_addr_tmp"] = None

    return df


# ---------- Upload sectie ----------
st.subheader("📂 Upload je bestanden")
col1, col2 = st.columns(2)

with col1:
    f_doel = st.file_uploader("Doelbestand (Data waar gewicht in moet)", type=["xlsx"])

with col2:
    f_bron = st.file_uploader("Bronbestand (Gewichtenbestand)", type=["xlsx"])

date_tol = st.slider("Datumtolerantie (dagen)", 0, 3, 1)

if f_doel and f_bron:
    # Lees bestanden
    df_doel = pd.read_excel(f_doel)
    originele_kolommen = list(df_doel.columns)  # originele structuur opslaan
    df_bron = pd.read_excel(f_bron)

    # ---------- Doelbestand voorbereiden ----------
    col_doel_datum = pick_col(df_doel, ["Periode", "Datum", "Uitvoerdatum"])
    col_doel_container = pick_col(df_doel, ["Inzamelmiddel", "Verpakkingstype", "Container type"])
    col_doel_afval = pick_col(df_doel, ["Afvalstroom", "Product", "Afvalstof"])

    if col_doel_datum is None or col_doel_container is None or col_doel_afval is None:
        st.error(
            "Het doelbestand mist één of meer benodigde kolommen.\n\n"
            f"Gevonden kolommen: {list(df_doel.columns)}"
        )
        st.stop()

    if "Gewicht" not in df_doel.columns:
        st.error("Het doelbestand bevat geen kolom 'Gewicht'.")
        st.stop()

    df_doel["Periode_dt"] = pd.to_datetime(df_doel[col_doel_datum], dayfirst=True, errors="coerce")
    df_doel["volume_tmp"] = df_doel[col_doel_container].apply(extract_volume)
    df_doel["afval_tmp"] = df_doel[col_doel_afval].apply(canon_afval)

    col_doel_loc_ref = pick_col(df_doel, [
        "Referentie locatie van herkomst",
        "Referentie",
        "Locatiecode"
    ])
    col_doel_loc_name = pick_col(df_doel, [
        "Naam locatie van herkomst",
        "Locatie",
        "Relatie"
    ])
    col_doel_loc_addr = pick_col(df_doel, [
        "Adres locatie van herkomst (Volledig)",
        "Adres"
    ])

    df_doel = build_loc_keys(
        df_doel,
        ref_col=col_doel_loc_ref,
        name_col=col_doel_loc_name,
        addr_col=col_doel_loc_addr,
        prefix="doel_"
    )

    # ---------- Bronbestand voorbereiden ----------
    col_datum = pick_col(df_bron, ["Datum", "Uitvoerdatum", "Uitvoer datum", "uitvoerdatum"])
    col_container = pick_col(df_bron, ["container type", "Container type", "Verpakkingstype", "Inzamelmiddel", "Containertype"])
    col_afval = pick_col(df_bron, ["afvalstof", "Afvalstof", "Product", "Afvalstroom"])
    col_hoeveelheid = pick_col(df_bron, ["Hoeveelheid", "Gewicht", "Aantal", "Netto gewicht", "Gewicht (kg)"])

    col_bron_loc_ref = pick_col(df_bron, [
        "Referentie locatie van herkomst",
        "Referentie",
        "Locatiecode"
    ])
    col_bron_loc_name = pick_col(df_bron, [
        "Naam locatie van herkomst",
        "Locatie",
        "Relatie"
    ])
    col_bron_loc_addr = pick_col(df_bron, [
        "Adres locatie van herkomst (Volledig)",
        "Adres"
    ])

    missing = [name for name, col in {
        "datum": col_datum,
        "container": col_container,
        "afval": col_afval,
        "hoeveelheid": col_hoeveelheid
    }.items() if col is None]

    if missing:
        st.error(
            "Het bronbestand mist één of meer benodigde velden. "
            f"Niet gevonden: {missing}\n\n"
            f"Gevonden kolommen: {list(df_bron.columns)}"
        )
        st.stop()

    df_bron["datum_dt"] = pd.to_datetime(df_bron[col_datum], dayfirst=True, errors="coerce")
    df_bron["volume_tmp"] = df_bron[col_container].apply(extract_volume)
    df_bron["afval_tmp"] = df_bron[col_afval].apply(canon_afval)
    df_bron["gewicht_tmp"] = df_bron[col_hoeveelheid].apply(parse_euro_number)

    df_bron = build_loc_keys(
        df_bron,
        ref_col=col_bron_loc_ref,
        name_col=col_bron_loc_name,
        addr_col=col_bron_loc_addr,
        prefix="bron_"
    )

    df_bron["used"] = False

    # ---------- Matching functie ----------
    def find_unique_match(d, v, a, doel_ref, doel_name, doel_addr, bron_df, tol_days=1):
        """Zoekt unieke match in bron_df en markeert als gebruikt."""

        if pd.isna(d) or pd.isna(v) or pd.isna(a):
            return None

        for delta in range(0, tol_days + 1):
            for sign in ([0] if delta == 0 else [-1, 1]):
                dt = d + timedelta(days=sign * delta) if sign != 0 else d

                base_mask = (
                    (bron_df["used"] == False)
                    & (bron_df["volume_tmp"] == v)
                    & (bron_df["afval_tmp"] == a)
                    & (bron_df["datum_dt"] == dt)
                )

                # 1. Eerst matchen op referentie
                if pd.notna(doel_ref):
                    mask_ref = base_mask & (bron_df["bron_loc_ref_tmp"] == doel_ref)
                    candidates = bron_df[mask_ref]
                    if len(candidates) == 1:
                        idx = candidates.index[0]
                        bron_df.loc[idx, "used"] = True
                        return bron_df.loc[idx, "gewicht_tmp"]

                # 2. Daarna op naam
                if pd.notna(doel_name):
                    mask_name = base_mask & (bron_df["bron_loc_name_tmp"] == doel_name)
                    candidates = bron_df[mask_name]
                    if len(candidates) == 1:
                        idx = candidates.index[0]
                        bron_df.loc[idx, "used"] = True
                        return bron_df.loc[idx, "gewicht_tmp"]

                # 3. Daarna op adres
                if pd.notna(doel_addr):
                    mask_addr = base_mask & (bron_df["bron_loc_addr_tmp"] == doel_addr)
                    candidates = bron_df[mask_addr]
                    if len(candidates) == 1:
                        idx = candidates.index[0]
                        bron_df.loc[idx, "used"] = True
                        return bron_df.loc[idx, "gewicht_tmp"]

                # 4. Alleen als er zonder locatie exact 1 kandidaat is
                candidates = bron_df[base_mask]
                if len(candidates) == 1:
                    idx = candidates.index[0]
                    bron_df.loc[idx, "used"] = True
                    return bron_df.loc[idx, "gewicht_tmp"]

        return None

    # ---------- Matching uitvoeren ----------
    st.subheader("🔄 Koppeling uitvoeren...")
    new_weights = []
    matched_rows = 0

    for _, r in df_doel.iterrows():
        w = find_unique_match(
            r["Periode_dt"],
            r["volume_tmp"],
            r["afval_tmp"],
            r["doel_loc_ref_tmp"],
            r["doel_loc_name_tmp"],
            r["doel_loc_addr_tmp"],
            df_bron,
            tol_days=date_tol
        )
        new_weights.append(w)
        if pd.notna(w):
            matched_rows += 1

    # ---------- Gewichten invullen ----------
    df_result = df_doel.copy()
    df_result["Gewicht"] = [fill_weight(c, n) for c, n in zip(df_result["Gewicht"], new_weights)]

    pct = round((matched_rows / len(df_result)) * 100, 2) if len(df_result) else 0
    st.metric("Succesvolle matches", f"{pct}%", f"{matched_rows} van {len(df_result)}")

    st.write("### 📊 Voorbeeld van ingevulde regels (eerste 15)")
    st.dataframe(df_result.head(15))

    # ---------- Niet-gebruikte regels uit BRON ----------
    hulpkolommen_bron = [
        "datum_dt", "volume_tmp", "afval_tmp", "gewicht_tmp",
        "bron_loc_ref_tmp", "bron_loc_name_tmp", "bron_loc_addr_tmp",
        "used"
    ]
    df_unmatched_bron = df_bron[df_bron["used"] == False].drop(
        columns=[c for c in hulpkolommen_bron if c in df_bron.columns],
        errors="ignore"
    )

    st.write("### 🧾 Niet-gekoppelde regels uit het gewichtenbestand")
    if df_unmatched_bron.empty:
        st.success("Alle regels uit het gewichtenbestand zijn gekoppeld ✅")
    else:
        st.warning(f"{len(df_unmatched_bron)} regels uit het gewichtenbestand konden niet gekoppeld worden.")
        st.dataframe(df_unmatched_bron)

    # ---------- Export ----------
    # Verwijder alle tijdelijke kolommen vóór export
    export_df = df_result[originele_kolommen].copy()

    # Zorg dat Gewicht numeriek is
    export_df["Gewicht"] = export_df["Gewicht"].apply(parse_euro_number)

    # Controle: kolommen exact gelijk?
    if list(export_df.columns) != originele_kolommen:
        st.error("❌ De kolomstructuur van het exportbestand komt niet exact overeen met het origineel!")
        st.stop()

    # Opslaan naar Excel (identieke structuur)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Sheet1")
        ws = writer.sheets["Sheet1"]

        # Geef kolom Gewicht notatie met 2 decimalen
        if "Gewicht" in export_df.columns:
            gewicht_col_idx = export_df.columns.get_loc("Gewicht") + 1  # 1-based index
            for row in range(2, len(export_df) + 2):  # rij 1 = header
                ws.cell(row=row, column=gewicht_col_idx).number_format = "0.00"

    output.seek(0)

    st.download_button(
        label="📥 Download resultaat (identiek aan origineel)",
        data=output,
        file_name="Data_met_gewichten.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("Upload beide bestanden om te starten.")