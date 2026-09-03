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
    m = re.search(r'(\d{2,4})\s*(?:l|ltr\.?|liter)\b', s)
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


def norm_code(x):
    """
    Normaliseert locatiecodes/referenties naar een schone string.

    BELANGRIJK: pandas leest numerieke kolommen soms in als float
    (bijv. 624510059.0). Zonder correctie zou het strippen van de punt
    een spookcijfer opleveren: '624510059.0' -> '6245100590', wat nooit
    matcht met de int-versie '624510059'. Daarom eerst hele floats naar
    int casten.
    """
    if pd.isna(x):
        return None

    # Float die eigenlijk een geheel getal is -> int (verwijdert de '.0')
    if isinstance(x, float) and x.is_integer():
        x = int(x)

    s = str(x).strip()

    # Vangnet: een resterende '.0' aan het eind weghalen (bijv. bij tekst-floats)
    s = re.sub(r'\.0+$', '', s)

    s = re.sub(r'[^0-9a-zA-Z]', '', s)
    return s if s else None


def clean_weight_value(x):
    """
    Neemt gewicht 1-op-1 over uit bronbestand.
    Verwijdert alleen overbodige spaties en een trailing komma.
    Voorbeelden:
    '90,'   -> '90'
    '167,'  -> '167'
    '210'   -> '210'
    90      -> '90'
    """
    if pd.isna(x):
        return None

    # Float die eigenlijk een geheel getal is -> int (voorkomt '90.0')
    if isinstance(x, float) and x.is_integer():
        x = int(x)

    s = str(x).strip()
    if s == "":
        return None

    s = s.replace("€", "").strip()

    # alleen trailing komma eraf
    if s.endswith(","):
        s = s[:-1]

    s = s.strip()
    return s if s != "" else None


def is_empty_or_zero(x):
    """Controleert of een bestaand gewicht leeg of 0 is."""
    if pd.isna(x):
        return True

    s = str(x).strip()
    if s == "":
        return True

    s = s.replace(",", ".")
    try:
        return float(s) == 0
    except:
        return False


def fill_weight(cur, new):
    """Vult gewicht alleen aan als huidige waarde leeg of 0 is."""
    if is_empty_or_zero(cur) and pd.notna(new):
        return new
    return cur


def pick_col(df, candidates):
    """Kiest de eerste bestaande kolom uit candidates."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def pick_weight_col(df, candidates):
    """
    Kiest uit candidates de kolom die het meest gevuld is (meeste
    niet-lege waarden). Voorkomt dat er per ongeluk een vrijwel lege
    kolom (bijv. 'Netto gewicht' met slechts 1 gevulde waarde) wordt
    gekozen boven een volledig gevulde kolom (bijv. 'Aantal').

    Bij gelijke vulling wint de volgorde in candidates (voorkeur).
    """
    aanwezig = [c for c in candidates if c in df.columns]
    if not aanwezig:
        return None
    # sorteer op aantal gevulde waarden (hoog eerst), stabiel dus
    # bij gelijkspel blijft de oorspronkelijke voorkeursvolgorde behouden
    beste = max(aanwezig, key=lambda c: df[c].notna().sum())
    return beste


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
    originele_kolommen = list(df_doel.columns)
    df_bron = pd.read_excel(f_bron)

    # ---------- Doelbestand voorbereiden ----------
    col_doel_datum = pick_col(df_doel, ["Periode", "Datum", "Uitvoerdatum"])
    col_doel_container = pick_col(df_doel, ["Inzamelmiddel", "Verpakkingstype", "Container type"])
    col_doel_afval = pick_col(df_doel, ["Afvalstroom", "Product", "Afvalstof"])
    col_doel_loc = pick_col(df_doel, ["Locatienummer", "Referentie locatie van herkomst", "Locatiecode", "Referentie"])

    missing_doel = [name for name, col in {
        "datum": col_doel_datum,
        "container": col_doel_container,
        "afval": col_doel_afval,
        "locatie": col_doel_loc
    }.items() if col is None]

    if missing_doel:
        st.error(
            "Het doelbestand mist één of meer benodigde kolommen. "
            f"Niet gevonden: {missing_doel}\n\n"
            f"Gevonden kolommen: {list(df_doel.columns)}"
        )
        st.stop()

    if "Gewicht" not in df_doel.columns:
        st.error("Het doelbestand bevat geen kolom 'Gewicht'.")
        st.stop()

    df_doel["Periode_dt"] = pd.to_datetime(df_doel[col_doel_datum], dayfirst=True, errors="coerce")
    df_doel["volume_tmp"] = df_doel[col_doel_container].apply(extract_volume)
    df_doel["afval_tmp"] = df_doel[col_doel_afval].apply(canon_afval)
    df_doel["loc_tmp"] = df_doel[col_doel_loc].apply(norm_code)

    # ---------- Bronbestand voorbereiden ----------
    col_bron_datum = pick_col(df_bron, ["Datum", "Uitvoerdatum", "Uitvoer datum", "uitvoerdatum"])
    col_bron_container = pick_col(df_bron, ["container type", "Container type", "Verpakkingstype", "Inzamelmiddel", "Containertype"])
    col_bron_afval = pick_col(df_bron, ["afvalstof", "Afvalstof", "Product", "Afvalstroom"])
    col_bron_gewicht = pick_weight_col(df_bron, ["Netto gewicht", "Gewicht (kg)", "Gewicht", "Hoeveelheid", "Aantal"])
    col_bron_loc = pick_col(df_bron, ["Referentie locatie van herkomst", "Locatienummer", "Locatiecode", "Referentie"])

    missing_bron = [name for name, col in {
        "datum": col_bron_datum,
        "container": col_bron_container,
        "afval": col_bron_afval,
        "gewicht": col_bron_gewicht,
        "locatie": col_bron_loc
    }.items() if col is None]

    if missing_bron:
        st.error(
            "Het bronbestand mist één of meer benodigde velden. "
            f"Niet gevonden: {missing_bron}\n\n"
            f"Gevonden kolommen: {list(df_bron.columns)}"
        )
        st.stop()

    st.caption(
        f"Gekozen gewichtskolom uit bron: **{col_bron_gewicht}** · "
        f"locatiekolom bron: **{col_bron_loc}** · locatiekolom doel: **{col_doel_loc}**"
    )

    df_bron["datum_dt"] = pd.to_datetime(df_bron[col_bron_datum], dayfirst=True, errors="coerce")
    df_bron["volume_tmp"] = df_bron[col_bron_container].apply(extract_volume)
    df_bron["afval_tmp"] = df_bron[col_bron_afval].apply(canon_afval)
    df_bron["loc_tmp"] = df_bron[col_bron_loc].apply(norm_code)
    df_bron["gewicht_tmp"] = df_bron[col_bron_gewicht].apply(clean_weight_value)
    df_bron["used"] = False

    # ---------- Matching functie ----------
    def find_unique_match(d, v, a, loc, bron_df, tol_days=1):
        """Zoekt unieke match in bron_df en markeert als gebruikt."""
        if pd.isna(d) or pd.isna(v) or pd.isna(a):
            return None

        for delta in range(0, tol_days + 1):
            for sign in ([0] if delta == 0 else [-1, 1]):
                dt = d + timedelta(days=sign * delta) if sign != 0 else d

                # 1. Strakke match: locatie + datum + volume + afval
                mask_strict = (
                    (bron_df["used"] == False)
                    & (bron_df["datum_dt"] == dt)
                    & (bron_df["loc_tmp"] == loc)
                    & (bron_df["volume_tmp"] == v)
                    & (bron_df["afval_tmp"] == a)
                )

                candidates = bron_df[mask_strict]
                if len(candidates) == 1:
                    idx = candidates.index[0]
                    bron_df.loc[idx, "used"] = True
                    return bron_df.loc[idx, "gewicht_tmp"]

                # 2. Fallback: datum + volume + afval, alleen als exact 1 resultaat
                mask_fallback = (
                    (bron_df["used"] == False)
                    & (bron_df["datum_dt"] == dt)
                    & (bron_df["volume_tmp"] == v)
                    & (bron_df["afval_tmp"] == a)
                )

                candidates = bron_df[mask_fallback]
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
            r["loc_tmp"],
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

    # ---------- Niet-gekoppelde regels uit DOEL ----------
    onbekende_idx = [i for i, w in enumerate(new_weights) if pd.isna(w)]
    if onbekende_idx:
        st.write("### ⚠️ Regels uit het doelbestand zonder gewicht")
        st.warning(f"{len(onbekende_idx)} regel(s) uit het doelbestand konden niet gekoppeld worden.")
        st.dataframe(df_doel.iloc[onbekende_idx][originele_kolommen])

    # ---------- Niet-gebruikte regels uit BRON ----------
    hulpkolommen_bron = ["datum_dt", "volume_tmp", "afval_tmp", "loc_tmp", "gewicht_tmp", "used"]
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
    # exact originele kolommen behouden
    export_df = df_result[originele_kolommen].copy()

    if list(export_df.columns) != originele_kolommen:
        st.error("❌ De kolomstructuur van het exportbestand komt niet exact overeen met het origineel!")
        st.stop()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False)

    output.seek(0)

    st.download_button(
        label="📥 Download resultaat (identiek aan origineel)",
        data=output,
        file_name="Data_met_gewichten.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("Upload beide bestanden om te starten.")
