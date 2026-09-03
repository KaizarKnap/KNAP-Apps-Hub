# --- Toegang: alleen ingelogde collega's (zie auth.py in de repo-root) ---
# Ook nodig op elke losse pagina: een pagina in pages/ is ook direct via
# haar eigen URL op te vragen.
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from auth import require_login

require_login()

import streamlit as st
import pandas as pd
import re
import extract_msg
from io import BytesIO

st.title("📧 Email Inkoop – ledigingsschema uit .msg-bestanden")

st.markdown("Upload één of meerdere `.msg`-bestanden en download het resultaat als Excel-bestand.")

uploaded_files = st.file_uploader(
    "Kies je .msg bestanden",
    type=["msg"],
    accept_multiple_files=True
)

def verwerk_msg(bestand):
    msg = extract_msg.Message(bestand)
    inhoud = msg.body

    blokken = re.split(r"(?=Afvalstroom:)", inhoud)
    rijen = []

    for blok in blokken:
        if "Afvalstroom:" not in blok:
            continue

        afvalstroom = re.search(r"Afvalstroom:\s*(.+)", blok)
        dienst = re.search(r"Dienst:\s*(.+)", blok)
        frequentie = re.search(r"Frequentie:\s*(.+)", blok)
        dagen = re.search(r"Dag\(en\):\s*(.+)", blok)
        startdatum = re.search(r"start vanaf:\s*(\d{2}-\d{2}-\d{4})", blok)
        adresblok = re.search(r"Dienstverleningsadres:\s*(.*?)\n\s*(.*?)\n\s*(.*)", blok)

        if adresblok:
            klantregel = adresblok.group(1).strip()
            match_klant = re.match(r"^(.*?)[\s\-]*\s*(\d+)$", klantregel)
            if match_klant:
                klantnaam = match_klant.group(1).strip()
                locatienummer = match_klant.group(2).strip()
            else:
                klantnaam = klantregel
                locatienummer = ""
        else:
            klantnaam = ""
            locatienummer = ""

        rijen.append({
            "Klantnaam": klantnaam,
            "Locatienummer": locatienummer,
            "Afvalstroom": afvalstroom.group(1).strip() if afvalstroom else "",
            "Dienst": dienst.group(1).strip() if dienst else "",
            "Frequentie": frequentie.group(1).strip() if frequentie else "",
            "Dag(en)": dagen.group(1).strip() if dagen else "",
            "Startdatum": startdatum.group(1).strip() if startdatum else "",
            "Straat": adresblok.group(2).strip() if adresblok else "",
            "Plaats": adresblok.group(3).strip() if adresblok else ""
        })

    return rijen

if uploaded_files:
    alle_rijen = []
    for bestand in uploaded_files:
        try:
            rijen = verwerk_msg(bestand)
            alle_rijen.extend(rijen)
            st.success(f"{bestand.name} verwerkt ({len(rijen)} records)")
        except Exception as e:
            st.error(f"Fout bij {bestand.name}: {e}")

    if alle_rijen:
        df = pd.DataFrame(alle_rijen)
        st.dataframe(df)

        # Excel downloaden
        buffer = BytesIO()
        df.to_excel(buffer, index=False)
        buffer.seek(0)

        st.download_button(
            label="📥 Download Excel-bestand",
            data=buffer,
            file_name="ledigingsschema_uitgelezen.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
