import streamlit as st

# 👉 importeer je losse apps als modules
import Email_Inkoop
import Extra_Kuub
import gratis_service_app
import RVKO_Gewichten
import Selfbilling

st.set_page_config(
    page_title="KNAP Apps Hub",
    layout="wide",
)

# 🔹 Klein CSS-blokje om de pagina breder te maken
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 1600px;  /* maak groter (bv. 1800) of gebruik 'none' voor echt full width */
        margin: 0 auto;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 🔹 SIDEBAR NAVIGATIE
st.sidebar.title("KNAP Apps Hub")
pagina = st.sidebar.radio(
    "Kies een tool:",
    (
        "🏠 Overzicht",
        "📧 Email_Inkoop",
        "🚛 Extra_Kuub",
        "🧾 gratis_service_app",
        "⚖️ RVKO_Gewichten",
        "💸 Selfbilling",
    ),
)

# 🔹 CENTRALE CONTENT OP BASIS VAN KEUZE
if pagina == "🏠 Overzicht":
    st.title("🧰 KNAP Apps Hub")

    st.markdown(
        """
Welkom bij de interne KNAP Apps hub.

Gebruik de **sidebar links** om een tool te kiezen:

- 📧 **Email_Inkoop** – Inkoop / ledigingsschema uit e-mails / .msg  
- 🚛 **Extra_Kuub** – Extra kuubs / extra bakken analyseren  
- 🧾 **gratis_service_app** – Gratis / niet-te-factureren service-orders  
- ⚖️ **RVKO_Gewichten** – RVKO gewichten koppelen / controleren  
- 💸 **Selfbilling** – Self-billing per leverancier  

Elke tool draait als aparte module, maar alles zit in deze ene hub.
"""
    )

    st.info(
        "ℹ️ Tip: gebruik de radio-knoppen in de sidebar om tussen tools te wisselen."
    )

elif pagina == "📧 Email_Inkoop":
    Email_Inkoop.run()

elif pagina == "🚛 Extra_Kuub":
    Extra_Kuub.run()

elif pagina == "🧾 gratis_service_app":
    gratis_service_app.run()

elif pagina == "⚖️ RVKO_Gewichten":
    RVKO_Gewichten.run()

elif pagina == "💸 Selfbilling":
    Selfbilling.run()
