"""Toegangscontrole voor de KNAP Apps Hub.

Collega's loggen in met hun Microsoft-werkaccount (Entra ID) via de ingebouwde
OIDC-ondersteuning van Streamlit. Er zijn dus geen wachtwoorden die wij zelf
beheren, opslaan of resetten.

Elke pagina begint met require_login(). Dat is geen dubbelop: een pagina in
pages/ is ook direct via haar eigen URL op te vragen, dus een check die alleen
in Home.py staat is te omzeilen.

Instellen: zie .streamlit/secrets.toml.example en docs/INLOGGEN.md.
"""

from __future__ import annotations

import os

import streamlit as st

PROVIDER = "microsoft"
STANDAARD_DOMEINEN = ["milieuservice.nl"]

# Alleen voor lokaal ontwikkelen zonder Entra-registratie:
#   PowerShell:  $env:KNAP_AUTH_DEV_BYPASS = "1"; streamlit run Home.py
# Bewust een omgevingsvariabele en geen secret, zodat dit nooit per ongeluk
# meelift met een secrets.toml die naar de server gaat.
DEV_BYPASS = os.environ.get("KNAP_AUTH_DEV_BYPASS") == "1"


# ---------------------------------------------------------------- secrets

def _secrets_sectie(naam: str) -> dict:
    """Geeft een secrets-sectie als dict. Leeg als secrets.toml ontbreekt."""
    try:
        return dict(st.secrets.get(naam, {}))
    except Exception:
        return {}


def _auth_ingesteld() -> bool:
    return PROVIDER in _secrets_sectie("auth")


# ---------------------------------------------------------------- identiteit

def huidige_email() -> str:
    """E-mailadres van de ingelogde gebruiker, lowercase. Leeg als onbekend.

    Entra ID levert het adres niet altijd in de 'email'-claim; bij accounts
    zonder mailbox zit het in preferred_username of upn.
    """
    for claim in ("email", "preferred_username", "upn", "unique_name"):
        waarde = getattr(st.user, claim, None)
        if isinstance(waarde, str) and "@" in waarde:
            return waarde.strip().lower()
    return ""


def huidige_naam() -> str:
    naam = getattr(st.user, "name", None)
    return naam if isinstance(naam, str) and naam else huidige_email()


def _mag_erin(email: str) -> bool:
    """Toegangsregels uit [access] in secrets.toml.

    domeinen: iedereen met een werkaccount in dit domein mag erin.
    emails:   losse uitzonderingen, bijvoorbeeld een externe accountant.
    """
    if not email:
        return False

    access = _secrets_sectie("access")
    domeinen = [str(d).strip().lower().lstrip("@") for d in access.get("domeinen", STANDAARD_DOMEINEN)]
    emails = [str(e).strip().lower() for e in access.get("emails", [])]

    domein = email.rsplit("@", 1)[-1]
    return domein in domeinen or email in emails


# ---------------------------------------------------------------- schermen

def _verberg_navigatie() -> None:
    """Sidebar met de app-lijst weghalen zolang er niemand is ingelogd."""
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"], div[data-testid="stSidebarNav"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _loginscherm() -> None:
    _verberg_navigatie()
    st.title("🔐 KNAP Apps Hub")
    st.write(
        "Deze apps werken met bedrijfsgegevens. Log in met je "
        "Milieu Service Nederland-account om verder te gaan."
    )
    if st.button("Inloggen met Microsoft", type="primary"):
        st.login(PROVIDER)
    st.caption("Vragen of geen toegang? Mail t.knap@milieuservice.nl")
    st.stop()


def _geen_toegang(email: str) -> None:
    _verberg_navigatie()
    st.title("⛔ Geen toegang")
    st.error(
        f"Het account **{email or 'onbekend'}** staat niet op de toegangslijst "
        "van de KNAP Apps Hub."
    )
    st.write("Vraag toegang aan via t.knap@milieuservice.nl.")
    if st.button("Uitloggen"):
        st.logout()
    st.stop()


def _setup_instructies() -> None:
    _verberg_navigatie()
    st.title("⚙️ Inloggen is nog niet ingesteld")
    st.warning(
        "Er is geen Microsoft-login geconfigureerd, dus de app blijft dicht. "
        "Dat is bewust: zonder configuratie zou iedereen bij de bedrijfsgegevens kunnen."
    )
    st.markdown(
        """
        **Wat er moet gebeuren**

        1. Vul `.streamlit/secrets.toml` (op de server: het secrets-veld van de hosting)
           volgens `.streamlit/secrets.toml.example`.
        2. De volledige stappen staan in `docs/INLOGGEN.md`.

        Alleen lokaal even zonder login werken? Zet `KNAP_AUTH_DEV_BYPASS=1` in je
        omgeving en herstart de app.
        """
    )
    st.stop()


def _sidebar(naam: str) -> None:
    with st.sidebar:
        st.markdown("---")
        st.caption(f"Ingelogd als **{naam}**")
        if st.button("Uitloggen", use_container_width=True):
            st.logout()


# ---------------------------------------------------------------- publiek

def require_login() -> str:
    """Blokkeert de pagina tot er een toegestane gebruiker is ingelogd.

    Aanroepen ná st.set_page_config en vóór de rest van de pagina.
    Geeft het e-mailadres van de ingelogde gebruiker terug.
    """
    if DEV_BYPASS:
        st.warning("⚠️ Login staat uit (KNAP_AUTH_DEV_BYPASS). Alleen voor lokaal testen.")
        return "dev@localhost"

    if not _auth_ingesteld():
        _setup_instructies()

    if not st.user.is_logged_in:
        _loginscherm()

    email = huidige_email()
    if not _mag_erin(email):
        _geen_toegang(email)

    _sidebar(huidige_naam())
    return email
