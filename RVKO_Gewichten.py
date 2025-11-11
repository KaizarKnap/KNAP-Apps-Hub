import streamlit as st
import pandas as pd
import io
import re
from datetime import timedelta

# GEEN st.set_page_config hier (dat gebeurt in Home.py)
def run():
    st.title("⚖️ RVKO Gewichten koppelen en controleren")

st.write("""
Deze app koppelt weeggegevens aan je data en vult automatisch de kolom **'Gewicht'** aan.  
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
    s = str(s).lower()
    if "bedrijfs" in s or "rest" in s:
        return "restafval"
    if "gft" in s:
        return "gft"
    if "papier" in s:
        return "papier"
    return re.sub(r'[^a-z0-9]', '', s)

def fill_weight(cur, new):
    """Vult gewicht aan als het leeg of nul is."""
    cur_num = pd.to_numeric(cur, errors="coerce")
    if (pd.isna(cur_num) or cur_num == 0) and pd.notna(new):
        return new
    return cur

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
    df_doel["Periode_dt"] = pd.to_datetime(df_doel["Periode"], dayfirst=True, errors="coerce")
    df_doel["volume_tmp"] = df_doel["Inzamelmiddel"].apply(extract_volume)
    df_doel["afval_tmp"] = df_doel["Afvalstroom"].apply(canon_afval)

    # ---------- Bronbestand voorbereiden ----------
    vereiste = ["Datum", "container type", "afvalstof", "Hoeveelheid"]
    if not all(col in df_bron.columns for col in vereiste):
        st.error(f"Het bronbestand mist een of meer vereiste kolommen: {vereiste}")
        st.stop()

    df_bron["datum_dt"] = pd.to_datetime(df_bron["Datum"], dayfirst=True, errors="coerce")
    df_bron["volume_tmp"] = df_bron["container type"].apply(extract_volume)
    df_bron["afval_tmp"] = df_bron["afvalstof"].apply(canon_afval)
    df_bron["used"] = False

    # ---------- Matching functie ----------
    def find_unique_match(d, v, a, bron_df, tol_days=1):
        """Zoekt unieke match in bron_df en markeert als gebruikt."""
        for delta in range(0, tol_days + 1):
            for sign in ([0] if delta == 0 else [-1, 1]):
                dt = d + timedelta(days=sign * delta) if sign != 0 else d
                mask = (
                    (bron_df["used"] == False)
                    & (bron_df["volume_tmp"] == v)
                    & (bron_df["afval_tmp"] == a)
                    & (bron_df["datum_dt"] == dt)
                )
                candidates = bron_df[mask]
                if not candidates.empty:
                    idx = candidates.index[0]
                    bron_df.loc[idx, "used"] = True
                    return bron_df.loc[idx, "Hoeveelheid"]
        return None

    # ---------- Matching uitvoeren ----------
    st.subheader("🔄 Koppeling uitvoeren...")
    new_weights = []
    matched_rows = 0

    for _, r in df_doel.iterrows():
        w = find_unique_match(r["Periode_dt"], r["volume_tmp"], r["afval_tmp"], df_bron, tol_days=date_tol)
        new_weights.append(w)
        if pd.notna(w):
            matched_rows += 1

    # ---------- Gewichten invullen ----------
    df_result = df_doel.copy()
    df_result["Gewicht"] = [fill_weight(c, n) for c, n in zip(df_result["Gewicht"], new_weights)]

    pct = round((matched_rows / len(df_result)) * 100, 2)
    st.metric("Succesvolle matches", f"{pct}%", f"{matched_rows} van {len(df_result)}")

    st.write("### 📊 Voorbeeld van ingevulde regels (eerste 15)")
    st.dataframe(df_result.head(15))

    # ---------- Niet-gebruikte regels uit BRON ----------
    df_unmatched_bron = df_bron[df_bron["used"] == False].drop(columns=["used"], errors="ignore")
    st.write("### 🧾 Niet-gekoppelde regels uit het gewichtenbestand")
    if df_unmatched_bron.empty:
        st.success("Alle regels uit het gewichtenbestand zijn gekoppeld ✅")
    else:
        st.warning(f"{len(df_unmatched_bron)} regels uit het gewichtenbestand konden niet gekoppeld worden.")
        st.dataframe(df_unmatched_bron)

    # ---------- Export ----------
    # Verwijder alle tijdelijke kolommen vóór export
    export_df = df_result[originele_kolommen].copy()

    # Controle: kolommen exact gelijk?
    if list(export_df.columns) != originele_kolommen:
        st.error("❌ De kolomstructuur van het exportbestand komt niet exact overeen met het origineel!")
        st.stop()

    # Opslaan naar Excel (identieke structuur)
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
