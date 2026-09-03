"""Toegangscontrole voor de KNAP Apps Hub.

Er zijn twee manieren om in te loggen. De app kiest zelf welke, op basis van
wat er in secrets.toml staat:

1. **Wachtwoord** - een gebruikersnaam en wachtwoord per collega, die jij
   uitdeelt. Werkt direct, zonder hulp van IT. Zet `[gebruikers]` in
   secrets.toml. Zie docs/INLOGGEN-WACHTWOORD.md.

2. **Microsoft-account** - collega's loggen in met hun eigen MSN-account en jij
   beheert geen enkel wachtwoord. Beter, maar vereist eenmalig een
   app-registratie in Entra ID. Zet `[auth.microsoft]` in secrets.toml.
   Zie docs/INLOGGEN.md.

Staat `[auth.microsoft]` volledig ingevuld, dan gaat die voor. Overstappen is
dus een kwestie van configuratie, niet van verbouwen.

Elke pagina begint met require_login(). Dat is geen dubbelop: een pagina in
pages/ is ook direct via haar eigen URL op te vragen, dus een check die alleen
in Home.py staat is te omzeilen.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets as secrets_module
import time

import streamlit as st

PROVIDER = "microsoft"
STANDAARD_DOMEINEN = ["milieuservice.nl"]
SESSIE_SLEUTEL = "knap_auth_gebruiker"

# PBKDF2-instellingen. Alleen uit de standaardbibliotheek, dus geen extra
# pakket dat op Streamlit Cloud kan omvallen.
ITERATIES = 210_000
HASH_PREFIX = "pbkdf2_sha256"

# Rem op wachtwoord-raden.
MAX_POGINGEN = 5
BLOKKADE_SECONDEN = 15 * 60

# Tekst uit secrets.toml.example. Staat dit er nog in, dan is het veld niet
# ingevuld en is de configuratie dus niet af.
PLACEHOLDERS = ("VUL_HIER", "TENANT_ID", "00000000-0000", "de-waarde-van")

# Alleen voor lokaal ontwikkelen zonder configuratie:
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


def _nog_niet_ingevuld(waarde) -> bool:
    tekst = str(waarde or "").strip()
    return not tekst or any(m in tekst for m in PLACEHOLDERS)


def _microsoft_ingesteld() -> bool:
    """True als alle velden die st.login nodig heeft echt gevuld zijn.

    Een half ingevulde secrets.toml is erger dan geen: st.login struikelt dan
    met een Authlib-fout in plaats van het uitlegscherm te tonen.
    """
    auth_sectie = _secrets_sectie("auth")
    provider = auth_sectie.get(PROVIDER)
    if not isinstance(provider, dict):
        return False

    verplicht = [
        auth_sectie.get("redirect_uri"),
        auth_sectie.get("cookie_secret"),
        provider.get("client_id"),
        provider.get("client_secret"),
        provider.get("server_metadata_url"),
    ]
    return not any(_nog_niet_ingevuld(v) for v in verplicht)


def _gebruikers() -> dict:
    """De ingestelde gebruikers: {gebruikersnaam: wachtwoordhash}."""
    return {
        str(naam).strip().lower(): str(hash_tekst)
        for naam, hash_tekst in _secrets_sectie("gebruikers").items()
        if not _nog_niet_ingevuld(hash_tekst)
    }


def _modus() -> str:
    """Welke inlogmanier actief is: 'microsoft', 'wachtwoord' of 'geen'."""
    if _microsoft_ingesteld():
        return "microsoft"
    if _gebruikers():
        return "wachtwoord"
    return "geen"


# ---------------------------------------------------------------- wachtwoorden

def maak_hash(wachtwoord: str, iteraties: int = ITERATIES) -> str:
    """Zet een wachtwoord om in een hash die veilig in secrets.toml kan.

    Uit de hash is het wachtwoord niet terug te rekenen. Ook iemand die de
    instellingen kan lezen, kent de wachtwoorden dus niet.
    """
    salt = secrets_module.token_bytes(16)
    berekend = hashlib.pbkdf2_hmac("sha256", wachtwoord.encode("utf-8"), salt, iteraties)
    return f"{HASH_PREFIX}${iteraties}${salt.hex()}${berekend.hex()}"


def _klopt_wachtwoord(hash_tekst: str, wachtwoord: str) -> bool:
    try:
        soort, iteraties, salt_hex, verwacht_hex = hash_tekst.split("$")
        if soort != HASH_PREFIX:
            return False
        berekend = hashlib.pbkdf2_hmac(
            "sha256", wachtwoord.encode("utf-8"), bytes.fromhex(salt_hex), int(iteraties)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(berekend.hex(), verwacht_hex)


def _verbrand_tijd(wachtwoord: str) -> None:
    """Rekent even door bij een onbekende gebruikersnaam.

    Zonder dit is een onbekende naam meetbaar sneller afgewezen dan een fout
    wachtwoord, en kan iemand daaraan aflezen welke namen bestaan.
    """
    hashlib.pbkdf2_hmac("sha256", wachtwoord.encode("utf-8"), b"x" * 16, ITERATIES)


@st.cache_resource
def _mislukte_pogingen() -> dict:
    """Gedeeld over alle sessies, zodat de rem niet te omzeilen is met F5."""
    return {}


def _is_geblokkeerd(gebruiker: str) -> int:
    """Resterende blokkade in seconden. 0 als er niets aan de hand is."""
    aantal, laatste = _mislukte_pogingen().get(gebruiker, (0, 0.0))
    if aantal < MAX_POGINGEN:
        return 0
    resterend = int(BLOKKADE_SECONDEN - (time.time() - laatste))
    return max(resterend, 0)


def _tel_mislukt(gebruiker: str) -> None:
    pogingen = _mislukte_pogingen()
    aantal, laatste = pogingen.get(gebruiker, (0, 0.0))
    if aantal >= MAX_POGINGEN and time.time() - laatste > BLOKKADE_SECONDEN:
        aantal = 0  # blokkade is verlopen, opnieuw beginnen
    pogingen[gebruiker] = (aantal + 1, time.time())


def _wis_pogingen(gebruiker: str) -> None:
    _mislukte_pogingen().pop(gebruiker, None)


# ------------------------------------------------------- identiteit (Microsoft)

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


def _beheer(titel: str = "🔧 Beheer: gebruiker toevoegen of wachtwoord wijzigen") -> None:
    """Maakt de regel die de beheerder in secrets.toml moet zetten.

    Staat bewust op het inlogscherm: zo heb je geen Python op je pc nodig om de
    eerste gebruiker aan te maken. Het is ook niet gevoelig, want hier komt
    alleen een hash uit; er is niets geheims uit te lezen.
    """
    with st.expander(titel, expanded=False):
        st.caption(
            "Alleen voor de beheerder. Typ een gebruikersnaam en wachtwoord; je "
            "krijgt een regel die je in de instellingen plakt. Het wachtwoord "
            "zelf wordt nergens opgeslagen."
        )

        if st.button("Stel een sterk wachtwoord voor"):
            tekens = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
            groepen = ["".join(secrets_module.choice(tekens) for _ in range(4)) for _ in range(4)]
            st.session_state["_beheer_voorstel"] = "-".join(groepen)

        voorstel = st.session_state.get("_beheer_voorstel")
        if voorstel:
            st.code(voorstel, language=None)
            st.caption("Geef dit wachtwoord aan je collega en typ het hieronder over.")

        naam = st.text_input("Gebruikersnaam", key="_beheer_naam", placeholder="p.jansen")
        wachtwoord = st.text_input("Wachtwoord", type="password", key="_beheer_wachtwoord")

        if st.button("Maak de regel"):
            schoon = naam.strip().lower()
            if not schoon or not wachtwoord:
                st.error("Vul zowel een gebruikersnaam als een wachtwoord in.")
            elif len(wachtwoord) < 12:
                st.error("Gebruik minstens 12 tekens. Korter is te makkelijk te raden.")
            else:
                st.success("Klaar. Plak de regel hieronder in de instellingen.")
                st.code(f'[gebruikers]\n"{schoon}" = "{maak_hash(wachtwoord)}"', language="toml")
                st.caption(
                    "Live: Streamlit Cloud, jouw app, Settings, Secrets. "
                    "Lokaal: .streamlit/secrets.toml. Heb je al gebruikers? Zet "
                    "dan alleen de onderste regel erbij; [gebruikers] hoeft maar "
                    "een keer."
                )


def _wachtwoord_login() -> None:
    _verberg_navigatie()
    st.title("🔐 KNAP Apps Hub")
    st.write("Log in om de apps te gebruiken.")

    with st.form("knap_inloggen"):
        naam = st.text_input("Gebruikersnaam")
        wachtwoord = st.text_input("Wachtwoord", type="password")
        verzonden = st.form_submit_button("Inloggen", type="primary")

    if verzonden:
        gebruiker = naam.strip().lower()
        resterend = _is_geblokkeerd(gebruiker)
        if resterend:
            st.error(
                f"Te veel mislukte pogingen. Probeer het over "
                f"{resterend // 60 + 1} minuten opnieuw."
            )
        else:
            hash_tekst = _gebruikers().get(gebruiker)
            # Een foutmelding voor beide gevallen: zo is niet af te lezen welke
            # gebruikersnamen bestaan.
            if hash_tekst and _klopt_wachtwoord(hash_tekst, wachtwoord):
                _wis_pogingen(gebruiker)
                st.session_state[SESSIE_SLEUTEL] = gebruiker
                st.rerun()
            else:
                if not hash_tekst:
                    _verbrand_tijd(wachtwoord)
                _tel_mislukt(gebruiker)
                st.error("Gebruikersnaam of wachtwoord klopt niet.")

    st.caption("Geen inloggegevens of wachtwoord vergeten? Mail t.knap@milieuservice.nl")
    _beheer()
    st.stop()


def _microsoft_login() -> None:
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
        "Er is nog geen enkele gebruiker ingesteld, dus de app blijft dicht. "
        "Dat is bewust: zonder configuratie zou iedereen bij de bedrijfsgegevens "
        "kunnen."
    )
    st.markdown(
        """
        **De snelste weg: een gebruiker aanmaken**

        1. Klap hieronder **Beheer** open en maak een gebruikersnaam met wachtwoord.
        2. Plak de regel die je krijgt in de instellingen:
           live in Streamlit Cloud onder **Settings > Secrets**,
           lokaal in `.streamlit/secrets.toml`.
        3. Herlaad de pagina. Klaar.

        Uitgebreide uitleg staat in `docs/INLOGGEN-WACHTWOORD.md`. Wil je liever
        dat collega's met hun eigen Microsoft-account inloggen, zodat jij geen
        wachtwoorden beheert? Dat staat in `docs/INLOGGEN.md`.
        """
    )
    _beheer("🔧 Beheer: eerste gebruiker aanmaken")
    st.stop()


def _sidebar(weergavenaam: str, via_provider: bool = False) -> None:
    with st.sidebar:
        st.markdown("---")
        st.caption(f"Ingelogd als **{weergavenaam}**")
        if st.button("Uitloggen", use_container_width=True):
            if via_provider:
                st.logout()
            else:
                st.session_state.pop(SESSIE_SLEUTEL, None)
                st.rerun()


# ---------------------------------------------------------------- publiek

def require_login() -> str:
    """Blokkeert de pagina tot er een toegestane gebruiker is ingelogd.

    Aanroepen na st.set_page_config en voor de rest van de pagina.
    Geeft de gebruikersnaam of het e-mailadres van de ingelogde gebruiker terug.
    """
    if DEV_BYPASS:
        st.warning("⚠️ Login staat uit (KNAP_AUTH_DEV_BYPASS). Alleen voor lokaal testen.")
        return "dev@localhost"

    modus = _modus()

    if modus == "microsoft":
        if not st.user.is_logged_in:
            _microsoft_login()
        email = huidige_email()
        if not _mag_erin(email):
            _geen_toegang(email)
        _sidebar(huidige_naam(), via_provider=True)
        return email

    if modus == "wachtwoord":
        gebruiker = st.session_state.get(SESSIE_SLEUTEL)
        # Opnieuw controleren: een gebruiker die uit de instellingen is
        # gehaald, is er bij de volgende klik ook echt uit.
        if not gebruiker or gebruiker not in _gebruikers():
            st.session_state.pop(SESSIE_SLEUTEL, None)
            _wachtwoord_login()
        _sidebar(gebruiker)
        return gebruiker

    _setup_instructies()
