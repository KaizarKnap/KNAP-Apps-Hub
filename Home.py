import streamlit as st

import Email_Inkoop
import Extra_Kuub
import gratis_service_app
import RVKO_Gewichten
import Selfbilling

st.set_page_config(
    page_title="KNAP Apps Hub",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 1600px;
        margin: 0 auto;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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

if pagina == "🏠 Overzicht":
    st.title("🧰 KNAP Apps Hub")
    st.markdown(
        """
Welkom bij de interne KNAP Apps hub.

Kies links in de sidebar welke tool je wilt gebruiken:

- 📧 **Email_Inkoop**
- 🚛 **Extra_Kuub**
- 🧾 **gratis_service_app**
- ⚖️ **RVKO_Gewichten**
- 💸 **Selfbilling**
"""
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
