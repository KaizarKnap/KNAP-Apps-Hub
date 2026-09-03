# Inloggen op de KNAP Apps Hub

Collega's loggen in met hun eigen Microsoft-werkaccount (Entra ID). Er zijn dus
geen wachtwoorden die wij zelf uitdelen, opslaan of resetten: wie al op zijn
laptop is ingelogd bij Milieu Service Nederland, klikt één keer op
"Inloggen met Microsoft" en is binnen.

## Hoe het in de code zit

| Bestand | Rol |
| --- | --- |
| `auth.py` | Het inlogscherm en de toegangsregels. Eén plek, niets dubbel. |
| `Home.py` en elke `pages/*.py` | Beginnen met `require_login()`. |
| `.streamlit/secrets.toml` | De inloggegevens. **Nooit committen** (staat in `.gitignore`). |
| `.streamlit/secrets.toml.example` | Voorbeeld met uitleg, mag wel in git. |

`require_login()` staat bewust in *elke* pagina en niet alleen in `Home.py`:
een pagina in `pages/` is ook direct via haar eigen URL op te vragen, dus een
check op alleen de hub is te omzeilen. Zonder geldige configuratie blijft de app
dicht — hij valt niet stil terug op "iedereen mag erin".

## Eenmalig instellen

### 1. App-registratie in Entra ID

In [portal.azure.com](https://portal.azure.com) → **Microsoft Entra ID** →
**App-registraties** → **Nieuwe registratie**:

- **Naam:** `KNAP Apps Hub`
- **Accounttypen:** *Alleen accounts in deze organisatiedirectory* (single tenant).
  Hiermee kan een account van buiten MSN niet eens een inlogpoging doen.
- **Omleidings-URI:** platform **Web**, waarde `http://localhost:8501/oauth2callback`

Heb je zelf geen rechten in de Azure-portal? Dan is dit het stukje dat je bij
IT moet aanvragen. Vraag om de drie waarden uit stap 2 en 3.

### 2. Waarden ophalen

Op het tabblad **Overzicht** van de registratie:

- **Toepassings-id (client)** → wordt `client_id`
- **Directory-id (tenant)** → vul je in de `server_metadata_url` in

### 3. Client secret maken

**Certificaten en geheimen** → **Nieuw clientgeheim**. Kies een looptijd en
kopieer de **waarde** direct: na het verlaten van de pagina is die niet meer
op te vragen.

> Een clientgeheim verloopt (maximaal 24 maanden). Zet de einddatum in je
> agenda, anders kan op die dag niemand meer inloggen.

### 4. secrets.toml vullen

Kopieer `.streamlit/secrets.toml.example` naar `.streamlit/secrets.toml` en vul
`client_id`, `client_secret` en het tenant-ID in. Genereer daarnaast een
`cookie_secret`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Live zetten

Op de server plak je dezelfde inhoud in het secrets-veld van de hosting
(bij Streamlit Cloud: **Settings → Secrets**) in plaats van in een bestand.
Twee dingen moeten dan mee:

1. `redirect_uri` wordt `https://<jouw-app-adres>/oauth2callback`
2. datzelfde adres moet je in Entra ID toevoegen onder
   **Verificatie → Omleidings-URI's**

Lokaal en live mogen naast elkaar bestaan: zet beide URI's in Entra ID en houd
per omgeving een eigen `redirect_uri`.

## Wie mag erin

Standaard: iedereen met een `@milieuservice.nl`-werkaccount. Aanpassen in
`[access]` van `secrets.toml`:

```toml
[access]
domeinen = ["milieuservice.nl"]
emails = ["externe.accountant@voorbeeld.nl"]
```

Wil je het beperken tot een handjevol collega's in plaats van de hele
organisatie, dan zijn er twee manieren:

- **Klein en simpel:** `domeinen = []` en de collega's los in `emails` zetten.
- **Netjes op termijn:** in Entra ID → **Bedrijfstoepassingen** → jouw app →
  **Eigenschappen** → *Toewijzing vereist* op **Ja**, en daarna een groep
  toewijzen. Toegang loopt dan mee met personeelswisselingen, zonder dat jij
  een lijst bijhoudt.

## Lokaal ontwikkelen zonder Entra

Even aan de app werken zonder registratie:

```bash
$env:KNAP_AUTH_DEV_BYPASS = "1"; streamlit run Home.py
```

De app zet dan een gele waarschuwing bovenaan. Dit is bewust een
omgevingsvariabele en geen instelling in `secrets.toml`, zodat het nooit per
ongeluk meelift naar de server.

## Als het niet werkt

| Wat je ziet | Waar het meestal aan ligt |
| --- | --- |
| "Inloggen is nog niet ingesteld" | `secrets.toml` ontbreekt of `[auth.microsoft]` staat er niet in. |
| Microsoft-foutmelding `AADSTS50011` | De `redirect_uri` staat niet exact zo in Entra ID (let op http vs https en de poort). |
| "Geen toegang" na inloggen | Het account valt buiten `domeinen`/`emails`, of Entra levert geen e-mailclaim — controleer of `scope = "openid profile email"` in de secrets staat. |
| Werkte gisteren, nu niet | Het clientgeheim is verlopen. Maak een nieuw geheim en werk de secrets bij. |
