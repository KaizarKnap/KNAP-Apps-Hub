# Inloggen met een wachtwoord

Dit is de eenvoudige manier: jij maakt een gebruikersnaam en wachtwoord per
collega aan, en deelt die uit. Je hebt geen Azure, geen IT en geen Python nodig.

> Wil je liever dat collega's met hun eigen Microsoft-account inloggen, zodat
> jij helemaal geen wachtwoorden beheert? Dat is de betere oplossing op termijn
> en staat in [INLOGGEN.md](INLOGGEN.md). Overstappen kan later zonder iets
> opnieuw te bouwen: je vult alleen andere velden in de instellingen in.

## De eerste gebruiker aanmaken

1. **Open de app.** Je ziet nu het scherm "Inloggen is nog niet ingesteld".
2. **Klap onderaan "Beheer" open.**
3. Klik eventueel op **Stel een sterk wachtwoord voor** en schrijf het over,
   of denk er zelf een uit van minstens 12 tekens.
4. Vul een **gebruikersnaam** in (bijvoorbeeld `t.knap`) en het wachtwoord.
5. Klik op **Maak de regel**. Je krijgt twee regels tekst te zien.
6. **Plak die twee regels in de instellingen:**
   - **Live:** Streamlit Cloud → jouw app → **Settings** → **Secrets**
   - **Lokaal:** onderaan `.streamlit/secrets.toml`
7. **Herlaad de pagina.** Je ziet nu een inlogscherm en kunt naar binnen.

Het resultaat ziet er zo uit:

```toml
[gebruikers]
"t.knap" = "pbkdf2_sha256$210000$3f1a...$9c4e..."
```

## Een collega toevoegen

Precies hetzelfde, maar nu vind je **Beheer** onderaan het inlogscherm. Maak de
regel, en zet **alleen de onderste regel** erbij in de instellingen —
`[gebruikers]` hoeft er maar één keer te staan:

```toml
[gebruikers]
"t.knap"   = "pbkdf2_sha256$210000$3f1a...$9c4e..."
"p.jansen" = "pbkdf2_sha256$210000$77bd...$1a52..."
```

Geef je collega drie dingen: het adres van de app, de gebruikersnaam en het
wachtwoord. Stuur het wachtwoord niet in dezelfde mail als het adres.

## Iemand de toegang afnemen

Haal de regel van die persoon weg uit de instellingen. Bij de eerstvolgende klik
staat diegene buiten, ook als hij al ingelogd was.

## Wachtwoord vergeten

Wachtwoorden zijn niet terug te lezen — ook niet door jou. Dat is bewust: in de
instellingen staat alleen een hash, en daar valt het wachtwoord niet uit te
herleiden. Maak dus via **Beheer** een nieuwe regel voor dezelfde
gebruikersnaam en vervang de oude regel.

## Wat je hier eerlijk over moet weten

Dit is een prima tussenstap en veel beter dan een app die open op internet
staat, maar het is niet hetzelfde als inloggen met een werkaccount:

| | Wachtwoord | Microsoft-account |
| --- | --- | --- |
| Instellen | 5 minuten, zelf | Eenmalig een app-registratie |
| Wachtwoord kwijt | Jij maakt een nieuwe | Regelt de collega zelf |
| Iemand uit dienst | Jij moet eraan denken | Loopt automatisch mee |
| Wachtwoord doorgegeven aan een derde | Merk je niet | Kan niet zomaar |
| Tweestapsverificatie | Nee | Ja, zoals overal bij MSN |

Praktisch: deel elk wachtwoord maar aan één persoon uit en gebruik niet één
gezamenlijk wachtwoord voor het hele team. Dan weet je bij problemen nog wie
waar bij kon.

## Hoe het technisch beveiligd is

- Wachtwoorden staan als **PBKDF2-HMAC-SHA256**-hash met 210.000 iteraties en
  een eigen salt per gebruiker. Alleen de standaardbibliotheek van Python, dus
  geen extra pakket dat op Streamlit Cloud kan omvallen.
- Vergelijken gebeurt met `hmac.compare_digest`, zodat de tijdsduur niets
  verraadt.
- Na **5 mislukte pogingen** is die gebruikersnaam **15 minuten** geblokkeerd.
  Die teller is gedeeld over alle sessies, dus F5 helpt een aanvaller niet.
- Een onbekende gebruikersnaam en een fout wachtwoord geven dezelfde melding en
  kosten dezelfde tijd. Zo is niet af te lezen welke namen bestaan.
- `require_login()` staat in **elke** pagina, niet alleen in `Home.py`: een
  pagina in `pages/` is ook direct via haar eigen URL op te vragen.

## Goed om te weten

- **Na het herladen van de pagina moet je opnieuw inloggen.** De sessie leeft in
  het geheugen van de browserverbinding en niet in een cookie. Tussen pagina's
  wisselen via de zijbalk gaat wel gewoon door.
- **Een gratis Community Cloud-app gaat in de slaapstand.** De eerste bezoeker
  daarna moet hem wakker laten worden; reken op een halve minuut.
- **Het "Beheer"-blok staat op het inlogscherm en is voor iedereen zichtbaar.**
  Dat kan veilig: daar komt alleen een hash uit een wachtwoord dat jij zelf
  intypt. Bestaande gebruikers of wachtwoorden zijn er niet mee op te vragen.
