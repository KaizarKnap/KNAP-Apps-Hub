# style_utils.py
from pathlib import Path
import streamlit as st

def load_css():
    """
    Laadt het bestand 'style.css' dat in dezelfde map staat als dit bestand
    en injecteert het in de Streamlit-app.
    Werkt voor zowel Home.py als de pagina's in /pages/.
    """
    css_file = Path(__file__).parent / "style.css"
    if css_file.exists():
        st.markdown(f"<style>{css_file.read_text()}</style>", unsafe_allow_html=True)
    else:
        st.warning("⚠️ style.css niet gevonden – standaard Streamlit-stijl wordt gebruikt.")
