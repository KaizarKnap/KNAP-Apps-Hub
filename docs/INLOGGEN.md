# Inloggen met een Microsoft-account

> Dit is de **beste** manier, maar hij vereist eenmalig een app-registratie in
> Entra ID en dus mogelijk hulp van IT. Wil je collega's vandaag aan het werk
> hebben, begin dan met [INLOGGEN-WACHTWOORD.md](INLOGGEN-WACHTWOORD.md) en kom
> hier later terug. Overstappen kost geen verbouwing: je vult alleen andere
> velden in de instellingen in.

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

`.streamlit/secrets.toml` staat al klaar met een gegenereerd `cookie_secret`.
Er moeten nog drie waarden in, alle drie uit stap 2 en 3:

| Veld | Waar het vandaan komt |
| --- | --- |
| `client_id` | Toepassings-id (client), tabblad Overzicht |
| `client_secret` | De **waarde** van het clientgeheim uit stap 3 |
| `server_metadata_url` | Vervang `TENANT_ID` door het Directory-id (tenant) |

Zolang er nog voorbeeldtekst in een van de vijf verplichte velden staat, telt
dat veld als leeg en houdt de app zichzelf dicht met het uitlegscherm. Dat is
bewust: een half ingevulde configuratie zou anders met een Authlib-foutmelding
crashen.

Moet je zelf een nieuw `cookie_secret` maken? In PowerShell, zonder Python:

```powershell
$b = New-Object byte[] 32; [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); ($b | ForEach-Object { $_.ToString('x2') }) -join ''
```

### 5. Live zetten op Streamlit Community Cloud

**Doe dit in deze volgorde.** Je hebt het definitieve app-adres nodig vóórdat
je de omleidings-URI in Entra ID kunt invullen, en dat adres kies je pas bij het
deployen. Achteraf een subdomein wijzigen breekt het inloggen.

1. **App-adres vastleggen.** Draait de app al op
   [share.streamlit.io](https://share.streamlit.io)? Neem dan het bestaande
   adres over. Zo niet: deploy hem vanaf de repo (`Home.py` als hoofdbestand) en
   kies bij **Custom subdomain** een naam die je niet meer wilt veranderen,
   bijvoorbeeld `knap-apps`. Je adres is dan
   `https://knap-apps.streamlit.app`.

2. **Omleidings-URI in Entra ID.** App-registratie → **Verificatie** →
   **URI toevoegen**:

   ```
   https://knap-apps.streamlit.app/oauth2callback
   ```

   Laat `http://localhost:8501/oauth2callback` er gewoon naast staan, dan blijft
   lokaal ontwikkelen werken. Het pad `/oauth2callback` en het adres moeten
   letterlijk kloppen — geen slash erachter, geen `www`.

3. **Secrets in het dashboard.** In Streamlit Cloud: jouw app → **Settings** →
   **Secrets**. Plak daar de inhoud van je `secrets.toml`, met één wijziging:

   ```toml
   redirect_uri = "https://knap-apps.streamlit.app/oauth2callback"
   ```

   Hier plak je het clientgeheim dus wél, maar in het dashboard van Streamlit en
   niet in de repo. Dat is het hele punt van `secrets.toml` in `.gitignore`:
   deze repo is publiek.

4. **Zelf testen in een privévenster.** Open de app in een incognitovenster.
   Je hoort het inlogscherm te zien, niet de hub. Probeer ook een pagina-URL
   rechtstreeks (`https://knap-apps.streamlit.app/Selfbilling`) — ook daar moet
   het inlogscherm komen.

De app mag daarna gewoon op een openbaar adres blijven staan: het slot zit in de
app zelf. Hem in Streamlit ook nog op *private* zetten met een lijst uitgenodigde
e-mailadressen voegt weinig toe en zorgt voor twee keer inloggen.

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

## Wat je collega's moet vertellen

- **Het adres** en dat ze inloggen met hun gewone MSN-account.
- **De eerste keer duurt even.** Een gratis Community Cloud-app gaat na een
  tijdje niets doen in de slaapstand. De eerste bezoeker daarna moet hem wakker
  laten worden; dat kost een halve minuut. Daarna is het snel.
- **De MOP-app onthoudt niets tussen sessies.** Zie de waarschuwing hieronder.

## Grenzen van de gratis versie

| Punt | Wat het betekent |
| --- | --- |
| **Slaapstand** | Na inactiviteit start de app opnieuw op bij de eerste bezoeker. |
| **MOPAPP-database verdwijnt** | Die schrijft naar `/tmp` (zie `pages/MOPAPP.py`). Bij elke herstart zijn geïmporteerde MOP-tarieven weg. Importeer ze per sessie opnieuw, of laat hier een echte database achter zetten. |
| **`data/tarieven/` ontbreekt** | Staat bewust niet in git, dus de tariefcontrole in Selfbilling werkt op de cloud alleen via handmatige upload. |
| **Geheugen** | Ongeveer 1 GB per app. Grote Excels in meerdere pagina's tegelijk kunnen de app laten herstarten. Bij twijfel: minder rijen, of `st.cache_data` gebruiken. |
| **Uploads zijn tijdelijk** | Bestanden die collega's uploaden worden in het geheugen verwerkt en niet opgeslagen. Dat is hier juist gunstig. |

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
