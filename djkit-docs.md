# djkit — Documentazione del framework

`djkit` ("Django kit") è il framework di funzioni generiche riusabili per progetti **Django + Django Ninja**.
Raccoglie ciò che serve a quasi ogni API: errori di dominio tradotti in HTTP, conferme delle operazioni
distruttive, registro delle operazioni, modifiche parziali, isolamento dei dati per utente, helper per date,
query, validazione, email e test. Si può includere come cartella in un progetto oppure installare come pacchetto pip.

> **Regola di aggiornamento:** questo file si aggiorna **nella stessa modifica** di ogni cambiamento a `djkit`:
> nuovi moduli o funzioni, firme cambiate, nuovi setting, funzioni rimosse. Lo stato di ogni voce passa da
> 📝 (progettato) a ✅ (implementato e testato).

Legenda: ✅ implementato e testato · 📝 progettato, non ancora implementato · 🗑️ deprecato

| Versione | Stato del framework |
|---|---|
| `0.1.0` (non ancora rilasciata) | in costruzione: tutti i moduli pronti tranne `mail` |

---

## 1. Principi e regole

1. **Dipendenze a senso unico.** `djkit` importa solo Django, Django Ninja e la libreria standard. Non importa
   **mai** il progetto che lo usa. Un test lo verifica (`djkit/tests/test_isolation.py`): ogni import di `djkit`
   deve puntare a `djkit`, `django`, `ninja`, `pydantic` o alla libreria standard.
2. **Nessun valore del progetto scritto nel codice.** Ciò che cambia da un progetto all'altro si passa come parametro
   oppure si legge da `settings` con un default: `getattr(settings, "DJKIT_...", default)`.
3. **Solo modelli astratti.** `djkit` non ha tabelle né migrazioni proprie: il progetto eredita i modelli astratti
   e crea le sue tabelle. Così l'estrazione come pacchetto non richiede migrazioni.
4. **Test propri.** I test stanno in `djkit/tests/` e passano da soli: `python manage.py test djkit`.
5. **Versione semantica.** `__version__` in `djkit/__init__.py`, con le modifiche annotate in `djkit/CHANGELOG.md`.
   - **MAJOR**: firme cambiate in modo incompatibile o funzioni rimosse.
   - **MINOR**: nuove funzioni o nuovi parametri opzionali.
   - **PATCH**: correzioni che non cambiano l'interfaccia.
6. **Documentazione.** Ogni funzione e classe ha una docstring in inglese. Questo file ne descrive struttura e uso.
7. **Cosa entra in `djkit`.** Un helper entra in `djkit` se funzionerebbe identico in qualunque progetto
   Django + Ninja, senza conoscerne il dominio. Altrimenti resta nel progetto.
8. **Testi per l'utente per chiave.** `djkit` non scrive mai un testo per l'utente direttamente nel codice: usa
   una chiave di `messages` con un testo predefinito in inglese, che il progetto sostituisce nella sua lingua con
   `DJKIT_MESSAGES` (§4.0). Anche i messaggi di Django, Ninja o Pydantic che arrivano all'utente passano da qui
   (handler di `api`, viste di `views`, validatori di `auth`). Ogni nuova chiave va documentata in §4.0.

---

## 2. Struttura

```
djkit/
├── __init__.py          # __version__
├── apps.py              # DjkitConfig (AppConfig)
├── CHANGELOG.md
├── djkit-docs.md        # questo file
├── messages.py          # messaggi per l'utente, per chiave (sostituibili con DJKIT_MESSAGES)
├── errors.py            # eccezioni di dominio e conferme
├── api.py               # handler HTTP delle eccezioni (anche di Ninja/Pydantic), schemi comuni, decoratori CSRF
├── views.py             # viste d'errore di Django in JSON (CSRF, 400, 403, 404, 500) e index.html della SPA
├── auth.py              # validazione password, login a sessione, validatori password, link di cambio password
├── audit.py             # registro delle operazioni (modello astratto + log_write, campi mascherati)
├── updates.py           # modifica parziale di un oggetto
├── fields.py            # campi a scelta, importi, vincoli CHECK
├── access.py            # permessi: policy unica, scope / check / get_accessible_or_404 (404 o 403)
├── workspaces.py        # spazi di lavoro separati (multi-tenancy): appartenenze con ruolo, spazio attivo, inviti
├── retention.py         # conservazione dei dati eliminati: data della cancellazione definitiva e dell'avviso
├── db.py                # QuerySet con filtro di accesso, eliminazione logica, subquery, controllo di unicità
├── dates.py             # date mensili, anniversari annuali
├── deadlines.py         # registro delle scadenze di un progetto (calendario, notifiche)
├── notices.py           # avvisi delle scadenze: preferenze per utente, già avvisati, finestre
├── validators.py        # normalizzazione di dati personali generici e dei testi in ingresso
├── it.py                # dati italiani: codice fiscale
├── dev.py               # comodità di sviluppo: interruttore della validazione allentata
├── mail.py              # invio email (testi da template) con modalità demo e domini bloccati
├── clients.py           # indirizzo del client (anche dietro proxy) e sua chiave anonima
├── numbers.py           # divisione di un totale in parti uguali o per pesi, trasferimenti minimi
├── pagination.py        # liste a pagine per numero di pagina (Django Ninja): ?page=&size=
├── texts.py             # catalogo dei testi per chiave, servito al frontend con ETag, chiavi esportate in TypeScript
├── management/commands/export_text_types.py   # comando che scrive le chiavi del catalogo in un file .ts
├── testing/
│   ├── runner.py        # VerboseTestRunner: output leggibile dei test
│   └── api.py           # helper per i test delle API
└── tests/               # test del framework
```

Dipendenze interne: `errors` → `messages`; `api` → `errors`, `messages`; `views` → `messages`;
`access` → `errors`; `auth` → `dev`, `errors`, `messages`; `db` → `errors`, `messages`; `audit` → `fields`, `messages`;
`updates` → `errors`, `messages`, `audit` (`snapshot`, `diff`); `it` → `dev`, `messages`; `workspaces` → `db`,
`errors`, `messages`; `retention` → nessuno; il comando `export_text_types` →
`texts`. Tutti gli altri moduli sono indipendenti tra loro.

`djkit` non ha un modulo `models`: i modelli astratti (`audit.AuditEntryBase`, `workspaces.WorkspaceModel`,
`workspaces.MembershipModel`, `workspaces.InvitationModel`) si importano dal loro modulo e
vanno usati solo durante il caricamento dei modelli del progetto (cioè dentro il suo `models.py`).

---

## 3. Installazione e configurazione in un progetto

```python
# settings.py
INSTALLED_APPS = [..., "djkit", ...]
TEST_RUNNER = "djkit.testing.runner.VerboseTestRunner"   # facoltativo
```

| Setting | Default | Usato da | Significato | Stato |
|---|---|---|---|---|
| `DJKIT_ACCESS_POLICY` | `None` (`AccessPolicy`: lettura e scrittura seguono `accessible_by`) | `access` | percorso puntato della sottoclasse di `access.AccessPolicy` con le regole del progetto | ✅ |
| `DJKIT_COOLDOWN_SECONDS` | `60` | `audit` | secondi minimi tra due invii verso l'esterno a proposito dello stesso oggetto (`ensure_cooldown`, `cooldown_until`); `0` = nessun blocco, negativo → `ImproperlyConfigured` | ✅ |
| `DJKIT_TEST_EXCLUDED_DIRS` | `{"tests", "migrations", ".venv", "venv", "site-packages"}` | `testing.runner` | parti di percorso mai mostrate come "codice sotto test"; il valore **sostituisce** il default. Le cartelle del modulo settings (da `SETTINGS_MODULE`, es. `config` per `config.settings`) sono sempre escluse in aggiunta | ✅ |
| `DJKIT_TEST_EXCLUDED_FILES` | `{"tests.py", "factories.py", "apps.py", "admin.py", "__init__.py"}` | `testing.runner` | nomi di file mai mostrati come "codice sotto test"; il valore **sostituisce** il default | ✅ |
| `DJKIT_TEST_PASSWORD_HASHERS` | `("django.contrib.auth.hashers.MD5PasswordHasher",)` | `testing.runner` | `PASSWORD_HASHERS` usati **solo durante i test**, al posto di quelli del progetto (lenti apposta: PBKDF2 impiega circa 0,5 s per hash). `None` lascia quelli del progetto | ✅ |
| `DJKIT_AUDIT_EXCLUDED_FIELDS` | `{"password"}` | `audit`, `updates` | campi mai scritti nel registro (né nelle `snapshot`, né nei `diff`); il valore **sostituisce** il default | ✅ |
| `DJKIT_AUDIT_MASKED_FIELDS` | `frozenset()` | `audit` | campi scritti nel registro con il valore **mascherato** (testo della chiave `audit_masked`; un valore vuoto resta vuoto): si vede che il campo è stato impostato o cambiato, mai il valore. Vale per i campi con quel nome in **ogni** modello (es. dati personali: `{"email", "phone"}`) | ✅ |
| `DJKIT_MESSAGES` | `{}` | `messages` (e quindi `errors`, `api`, `views`, `auth`, `db`, `updates`) | testi dei messaggi per l'utente, `{chiave: testo}`; le chiavi assenti restano col testo inglese di `DEFAULT_MESSAGES`. Un progetto in un'altra lingua le fornisce **tutte** (vedi §4.0) | ✅ |
| `DJKIT_SPA_INDEX` | nessuno (obbligatorio per `spa_index`) | `views` | percorso dell'`index.html` della build della SPA | ✅ |
| `DJKIT_RELAXED_VALIDATION` | `False` | `dev` (e quindi `auth`, `it`) | solo sviluppo: password senza regole, codice fiscale da 1 a 16 caratteri; con `DEBUG` spento → `ImproperlyConfigured`; spento durante i test | ✅ |
| `DJKIT_MAIL_DEMO_MODE` | `False` | `mail` | se vero `send_email` non invia e registra nel log destinatari e oggetto (istanze dimostrative) | ✅ |
| `DJKIT_MAIL_BLOCKED_DOMAINS` | `RESERVED_DOMAINS` | `mail` | domini (e sottodomini) a cui `send_email` non scrive mai; `[]` = nessun blocco | ✅ |

Setting di Django usati: `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL` (`mail`); `PASSWORD_RESET_TIMEOUT` (`auth`, validità dei
link di cambio password, in secondi).

`BASE_DIR` (setting standard dei progetti Django) è usato da `testing.runner` per decidere quali file appartengono
al progetto.

---

## 4. Moduli e funzionalità

### 4.0 `messages` — Messaggi per l'utente ✅

Ogni testo che `djkit` può mostrare all'utente finale (dettaglio degli errori, errori dei campi, messaggi dei
validatori, errori HTTP di Ninja/Pydantic) ha una **chiave** e un testo predefinito **in inglese** in
`DEFAULT_MESSAGES`. Il progetto mostra la propria lingua fornendo i testi nel setting `DJKIT_MESSAGES`: il codice
di `djkit` resta in inglese, ma nessun messaggio inglese arriva all'utente.

- `DEFAULT_MESSAGES: dict[str, str]`: chiave → testo inglese. Gruppi di chiavi:
  - eccezioni: `domain_error`, `not_found`, `conflict`, `invalid_data`, `confirmation_required`;
  - `db`/`updates`: `unique`, `field_not_editable`, `deleted_read_only`;
  - `workspaces`: `workspace_not_found`, `invitation_not_found`;
  - `audit`: `audit_masked` (valore di un campo mascherato);
  - `auth`: `login_failed`, `password_too_short` (`{min_length}`), `password_too_similar`, `password_reset_invalid`;
  - errori HTTP: `bad_request`, `unauthorized`, `forbidden`, `csrf_failed`, `method_not_allowed`,
    `too_many_requests`, `server_error`;
  - validazione degli schemi: `missing`, `invalid_value`, `invalid_json`, `string_type`, `string_too_short`
    (`{min_length}`), `string_too_long` (`{max_length}`), `list_too_short` (`{min_length}`, elementi di un elenco),
    `list_too_long` (`{max_length}`), `number_type`, `boolean_type`, `date_type`,
    `datetime_type`, `greater_than` (`{gt}`), `greater_than_equal` (`{ge}`), `less_than` (`{lt}`),
    `less_than_equal` (`{le}`), `max_digits` (`{max_digits}`), `decimal_places` (`{decimal_places}`), `choice`,
    `list_type`, `object_type`, `unknown_field` (campo non dichiarato dallo schema, vedi `InputSchema`);
  - `it`: `tax_code_invalid` (`{length}`).
- `get_message(key: str, **params) -> str`: testo del progetto (`DJKIT_MESSAGES`) o quello inglese, con i
  segnaposto `{nome}` riempiti (`str.format`); se manca il valore di un segnaposto restituisce il testo così com'è.
  Chiave sconosciuta → `KeyError`. Accetta anche chiavi definite solo dal progetto in `DJKIT_MESSAGES`.
- `missing_messages() -> list[str]`: chiavi di `DEFAULT_MESSAGES` che il progetto non ha fornito, ordinate. Un
  progetto che non deve mai mostrare i testi inglesi verifica in un test che la lista sia vuota.
- `configured_messages() -> dict[str, str]`: il setting `DJKIT_MESSAGES` (o `{}`).

```python
# settings.py
DJKIT_MESSAGES = {"not_found": "Elemento non trovato.", "string_too_short": "Inserisci almeno {min_length} caratteri.", ...}

get_message("string_too_short", min_length=3)   # "Inserisci almeno 3 caratteri."
```

Quando si aggiunge una chiave a `DEFAULT_MESSAGES`, il progetto deve aggiungere il suo testo (il test su
`missing_messages()` lo segnala).

### 4.1 `errors` — Eccezioni di dominio e conferme ✅

I service sollevano queste eccezioni senza conoscere HTTP. Le traduce in risposte `api.register_error_handlers`.

| Nome | Status HTTP | `message_key` (testo inglese) | Quando |
|---|---|---|---|
| `DomainError(detail=None, **extra)` | 400 | `domain_error` (`Request failed.`) | classe base |
| `Forbidden` | 403 | `read_only` (`You can only consult this item: you cannot change it.`) | l'utente vede l'oggetto ma non può modificarlo (sola lettura, vedi `access`): la sua esistenza non è un segreto |
| `NotFound` | 404 | `not_found` (`Not found.`) | oggetto inesistente **o non accessibile** all'utente: non si rivela che esiste |
| `Conflict` | 409 | `conflict` (`Conflict with the current state.`) | conflitto con lo stato attuale (valore già usato, oggetto in sola lettura, ...) |
| `InvalidData` | 422 | `invalid_data` (`Invalid data.`) | violazione di una regola non coperta dalla validazione dello schema |
| `ConfirmationRequired(impact, required, given, detail=None)` | 428 | `confirmation_required` (`Confirmation required.`) | operazione distruttiva non ancora confermata abbastanza volte |
| `TooManyRequests(retry_at, detail=None)` | 429 | `too_many_requests` (`Too many requests: try again later.`) | la stessa operazione ripetuta troppo presto (es. un secondo invio dentro il blocco di `audit.ensure_cooldown`); nel corpo `retry_at` (ISO) dice da quando si può riprovare |

- Ogni eccezione ha `detail` (messaggio per l'utente; se manca, `get_message(message_key)` della classe, quindi
  il testo di `DJKIT_MESSAGES` se il progetto lo fornisce) ed `extra`
  (dati aggiuntivi per il corpo della risposta; i valori `None` vengono scartati).
  `payload() -> dict` restituisce `{"detail": ..., **extra}`.
- `InvalidData(detail=None, errors={"campo": ["messaggio", ...]})`: errori legati ai campi.
- `InvalidData.from_validation_error(error, field_prefix="") -> InvalidData`: converte una `ValidationError` di Django.
  Gli errori dei campi finiscono in `errors` (quelli generali sotto `"__all__"`), gli altri messaggi in `detail`.
  Con `field_prefix` (oggetto annidato nel corpo della richiesta, es. `"customer."`) i campi diventano
  `"customer.email"` e gli errori generali finiscono sotto `"customer"`.
- `prefixed_field(field, prefix) -> str`: il nome di campo usato da `from_validation_error` con un prefisso.
- `require_confirmation(given: int, required: int, impact: dict, detail: str | None = None) -> None`: solleva
  `ConfirmationRequired` se `given < required`, altrimenti non fa nulla. `impact` riassume cosa verrebbe perso,
  per esempio `{"orders": 3, "invoices": 12}`.

```python
require_confirmation(payload.confirmations, 2 if has_money_rows else 1, impact)
```

### 4.2 `api` — Integrazione con Django Ninja ✅

- `register_error_handlers(api: NinjaAPI, status_codes: dict | None = None) -> None`: registra gli handler
  degli errori; il corpo della risposta è sempre `ErrorOut` e i testi vengono da `messages`.
  - Ogni eccezione di `errors` (`DEFAULT_STATUS_CODES`) → `exc.payload()` col suo status. `status_codes` aggiunge
    o sostituisce degli status, per esempio `{PaymentRequired: 402}` per un'eccezione del progetto. Una
    sottoclasse non registrata usa lo status della classe registrata più vicina, perché Ninja cerca l'handler
    lungo l'MRO.
  - `ValidationError` di Django → 422 di `InvalidData.from_validation_error`.
  - `ValidationError` di Ninja (validazione degli schemi con Pydantic) → 422 `{detail: invalid_data, errors:
    validation_errors(...)}`: stesso formato degli altri 422, invece della lista di Pydantic con i messaggi inglesi.
  - `HttpError` di Ninja → il suo status con `http_error_message(exc)`: `AuthenticationError` 401
    (`unauthorized`), controllo CSRF fallito della sessione 403 (`csrf_failed`), corpo non leggibile 400
    (`invalid_json`), `Throttled` 429 (`too_many_requests`), altri status da `HTTP_ERROR_MESSAGE_KEYS`.
  - `Http404` sollevato dentro un'operazione → 404 `not_found`.
- `http_error_message(exc) -> str`: messaggio per l'utente di un `HttpError` di Ninja (i messaggi di Ninja,
  per esempio `"Unauthorized"`, non vengono mai mostrati).
- `validation_errors(errors: list[dict]) -> dict[str, list[str]]`: errori di Ninja/Pydantic → `{campo: [messaggi]}`.
  - `error_field(loc) -> str`: nome del campo dalla posizione dell'errore, senza la sorgente e il nome del
    parametro (`("body", "payload", "email")` → `"email"`, `("query", "usable")` → `"usable"`, annidati con il
    punto `"items.0.amount"`, nessun campo → `NON_FIELD_ERRORS = "__all__"`).
  - `validation_message(error) -> str`: messaggio per tipo di errore Pydantic (`VALIDATION_MESSAGE_KEYS`, con i
    segnaposto presi da `ctx`, per esempio `{min_length}`); per `value_error` (un validatore personalizzato che
    solleva `ValueError`) il messaggio del validatore stesso; un testo vuoto dove serve almeno un carattere
    (`string_too_short` con `min_length` 1) → `missing` ("Campo obbligatorio.", non "almeno 1 caratteri"); tipi
    sconosciuti → `invalid_value`.
- `ErrorOut`: schema `{detail: str, errors?: {campo: [str]}, impact?: dict, required?: int, given?: int}`.
- `InputSchema`: base degli schemi dei **corpi delle richieste** (`model_config = ConfigDict(extra="forbid")`). Un
  campo che lo schema non dichiara risponde 422 su quel campo con la chiave `unknown_field` (anche dentro un elenco:
  `"0.role"`), invece di essere scartato in silenzio: un client che sbaglia il nome di un campo, o manda un campo che
  quell'endpoint non modifica, se ne accorge subito. Gli schemi delle risposte restano `ninja.Schema`.
- `ConfirmationIn` (un `InputSchema`): schema `{confirmations: int = 0}` (≥ 0), il numero di conferme date dal client.
  `{"confirmation": 2}` (errore di battitura) → 422, non un 428 con 0 conferme.
- `csrf_protected`: decoratore di operazione (`decorate_view(csrf_protect)`) che impone il controllo CSRF di
  Django. Serve sugli endpoint pubblici con `auth=None` che modificano lo stato (login, registrazione): Ninja
  controlla il token CSRF solo dentro l'autenticazione a sessione (`django_auth`), quindi senza il decoratore
  questi endpoint accetterebbero richieste da altri siti. Token assente o errato → 403.
- `sets_csrf_cookie`: decoratore di operazione (`decorate_view(ensure_csrf_cookie)`) che invia sempre il cookie
  CSRF nella risposta, così un client single-page può leggerlo e rimandarlo nell'header.

```python
api = NinjaAPI(auth=django_auth)   # django_auth (cookie di sessione) controlla già il token CSRF
register_error_handlers(api)

@api.get("/csrf", auth=None, response={204: None})
@sets_csrf_cookie
def csrf(request):
    return 204, None

@api.post("/login", auth=None)
@csrf_protected
def login(request, payload: LoginIn): ...
```

### 4.2a `views` — Viste d'errore di Django in JSON ✅

Alcuni errori Django li risponde fuori da qualunque API, con pagine HTML non sempre nella lingua dell'utente: il
controllo CSRF fallito di `csrf_protect` (per esempio `api.csrf_protected`) e, con `DEBUG` spento, le pagine 400,
403, 404 e 500. Queste viste rispondono invece `{"detail": messaggio}` con i testi di `messages`.

- `csrf_failure(request, reason="")` → 403 `csrf_failed` (per `CSRF_FAILURE_VIEW`; `reason` è il motivo tecnico,
  non mostrato).
- `bad_request` → 400 `bad_request`; `permission_denied` → 403 `forbidden`; `page_not_found` → 404 `not_found`;
  `server_error` → 500 `server_error` (per `handler400`/`handler403`/`handler404`/`handler500`).
- `error_response(key, status) -> JsonResponse`: la risposta comune.
- `spa_index(request) -> HttpResponse` ✅: rotta finale che serve l'`index.html` della build di una single-page application (percorso in `DJKIT_SPA_INDEX`), così le rotte del client funzionano anche ricaricando la pagina. Il file è letto a ogni richiesta (una nuova build si vede senza riavviare) con `Cache-Control: no-cache`. File assente → 404 `not_found` e una riga di log `ERROR`; setting assente → `ImproperlyConfigured`. Uso: `re_path(r"^", spa_index)` come ultima rotta.

```python
# settings.py
CSRF_FAILURE_VIEW = "djkit.views.csrf_failure"
# urls.py (URLconf principale)
handler404 = "djkit.views.page_not_found"   # e così handler400, handler403, handler500
```

Con `DEBUG` attivo Django continua a mostrare le sue pagine tecniche di 404 e 500. Per avere il 404 in JSON sotto
il prefisso dell'API in ogni modalità, si aggiunge `page_not_found` come rotta finale dopo l'API (ci arriva solo un
indirizzo che nessun endpoint riconosce):

```python
urlpatterns = [path("api/", api.urls), re_path(r"^api/", page_not_found)]
```

### 4.2b `auth` — Password e login a sessione ✅

Funzionano con qualunque modello utente (usano solo `django.contrib.auth`).

- `validate_new_password(password: str, user=None, field: str = "password") -> None`: applica
  `AUTH_PASSWORD_VALIDATORS`; se la password non va bene solleva `InvalidData(errors={field: [messaggi]})`.
  `user` (anche non ancora salvato) permette ai validatori di confrontare la password con i dati dell'utente.
  Con `dev.relaxed_validation()` attivo (solo sviluppo) accetta qualunque password.
- `login_with_password(request, username: str, password: str, detail: str | None = None) -> user`:
  `authenticate()` + `login()` (imposta il cookie di sessione). Credenziali errate o utente non attivo →
  `InvalidData` con lo stesso messaggio (`detail`, oppure la chiave `login_failed`), così non si rivela se
  l'account esiste. `username` è il valore di `USERNAME_FIELD`, già normalizzato dal chiamante.
- `MinimumLengthValidator` e `UserAttributeSimilarityValidator`: sostituti dei validatori di Django con le stesse
  regole e opzioni, ma con i messaggi di `messages` (`password_too_short` con `{min_length}`,
  `password_too_similar`). Servono perché la versione di Django del primo può restare non tradotta (forma
  plurale) e il secondo inserisce nel testo il `verbose_name` del campo dell'utente, spesso in un'altra lingua.

```python
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "djkit.auth.UserAttributeSimilarityValidator"},
    {"NAME": "djkit.auth.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
```

```python
user = login_with_password(request, normalize_email_address(payload.email), payload.password)
```

Cambio password con un link inviato per email (password dimenticata, o un utente che la vuole cambiare). Usano
`default_token_generator` di Django: il token dipende dall'hash della password, dall'ultimo login e dall'email,
quindi vale **una volta sola** (cambiata la password non funziona più) e per `PASSWORD_RESET_TIMEOUT` secondi.

- `password_reset_token(user) -> tuple[str, str]`: `(uid, token)`, la chiave dell'utente in base64 per URL e il token.
  Il progetto li mette nel link che invia.
- `user_for_password_reset(uid: str, token: str, detail: str | None = None) -> user`: l'utente del link, attivo e
  con il token valido. Altrimenti (uid malformato, utente inesistente o non attivo, token sbagliato, scaduto o già
  usato) `InvalidData` sempre con lo stesso messaggio (`detail`, oppure la chiave `password_reset_invalid`).
- `reset_password(uid, token, new_password, field="new_password", detail=None) -> user`: controlla il link, applica
  i validatori (errori su `field`), salva la nuova password. Le sessioni aperte prima smettono di funzionare (Django
  confronta l'hash della sessione a ogni richiesta).

```python
uid, token = password_reset_token(user)
link = f"{settings.FRONTEND_RESET_URL}?{urlencode({'uid': uid, 'token': token})}"
...
reset_password(payload.uid, payload.token, payload.new_password)   # dalla pagina del link
```

Chi chiede il link dovrebbe ricevere sempre la stessa risposta, registrato o no, per non rivelare quali email hanno
un account: è compito del progetto.

### 4.3 `audit` — Registro delle operazioni ✅

- `AuditAction`: valori ammessi di `action` (`CREATE`, `UPDATE`, `DELETE`, `NOTIFY`). `NOTIFY` registra un messaggio
  inviato a proposito di una riga (per esempio un'email di sollecito): la riga non cambia, ma gli utenti vogliono sapere
  che è stato inviato.
- `ActorKind`: chi ha scritto la voce, `USER` (un utente) o `BATCH` (un'attività automatica, per esempio un comando
  lanciato ogni giorno, che non ha un utente).
- `AuditEntryBase` (modello **astratto**):

  | Campo | Tipo | Significato |
  |---|---|---|
  | `actor` | FK a `AUTH_USER_MODEL`, `SET_NULL`, `related_name="%(app_label)s_%(class)s_entries"` | chi ha fatto la modifica (`None` se l'utente è stato eliminato; sempre `None` per `BATCH`) |
  | `actor_kind` | `choice_field(ActorKind)`, default `USER` | utente o attività automatica |
  | `action` | `choice_field(AuditAction)` | tipo di operazione |
  | `model` | `CharField(100)` | nome del modello modificato |
  | `object_id` | `PositiveBigIntegerField`, null | chiave dell'oggetto |
  | `object_label` | `CharField(300)` | `str(obj)` al momento della modifica |
  | `changes` | `JSONField` | `{"campo": [vecchio, nuovo]}` oppure la `snapshot` |
  | `timestamp` | `DateTimeField(auto_now_add)` | quando |

  Nel `Meta` sono definiti: ordinamento dal più recente, `verbose_name` "audit log entry" e i vincoli CHECK
  `"<app>_<classe>_action_valid"`, `"<app>_<classe>_actor_kind_valid"` e `"<app>_<classe>_batch_without_actor"` (una
  voce `BATCH` non ha `actor`). Se la sottoclasse ridefinisce `Meta.constraints`, deve rimetterli con
  `AuditEntryBase.action_constraint(name)` e `*AuditEntryBase.actor_kind_constraints(prefix)`.

  Il `related_name` di `actor` è diverso per ogni sottoclasse: per `shop.OrderLog` vale
  `user.shop_orderlog_entries`. Così un progetto può avere più modelli concreti di registro senza conflitti
  (errori `fields.E304` / `E305`) e senza ridefinire `actor`.

```python
class AuditLogEntry(AuditEntryBase):
    team_id = models.PositiveBigIntegerField(null=True)

log_write(AuditLogEntry, request.user, AuditAction.UPDATE, invoice, changes, team_id=invoice.team_id)
```

- `log_write(entry_model, actor, action, obj, changes=None, *, actor_kind=ActorKind.USER, **context) -> AuditEntryBase`:
  crea una voce del registro e va chiamata dentro la stessa transazione della scrittura. Per `DELETE` va chiamata
  **prima** di `obj.delete()`.
  - Se `changes` è `None`, salva la `snapshot` completa per `CREATE` e `DELETE` e `{}` per `UPDATE` e `NOTIFY`.
  - Con `actor_kind=ActorKind.BATCH` (attività automatica) `actor` deve essere `None`, altrimenti `ValueError`.
- `last_logged_at(entries, object_ids) -> dict`: per ogni oggetto, l'ora della sua voce più recente tra `entries` (un
  QuerySet di voci già filtrato da chi chiama: modello, azione, `changes`...), con una sola query; gli oggetti senza
  voci mancano. Serve per esempio a distanziare i promemoria inviati a proposito di una riga:

  ```python
  sent = OrderLog.objects.filter(model="Customer", action=AuditAction.NOTIFY, changes__delivered=True)
  last = last_logged_at(sent, [c.pk for c in customers])   # {customer_id: datetime}
  ```
- **Blocco anti-spam breve (facoltativo)**: impedisce due invii verso l'esterno (email, SMS, webhook...) a proposito dello
  stesso oggetto a meno di `DJKIT_COOLDOWN_SECONDS` secondi (default `DEFAULT_COOLDOWN_SECONDS` = 60, il valore più
  diffuso nei servizi di email e OTP; non esiste uno standard ufficiale; `0` lo spegne, negativo →
  `ImproperlyConfigured`). Ferma doppi clic, tentativi ripetuti e due utenti che inviano nello stesso momento. Non usa
  tabelle proprie: legge il registro. **Requisiti, solo per chi lo usa:** ogni invio lascia una voce nel registro
  (es. `NOTIFY`) nella stessa transazione dell'invio, e il controllo si fa con la riga dell'oggetto bloccata
  (`select_for_update`), così due richieste simultanee non passano entrambe.
  - `cooldown_seconds() -> int`: l'intervallo dal setting.
  - `cooldown_until(entries, object_id, seconds=None) -> datetime | None`: fino a quando l'invio è bloccato, `None` se
    è permesso ora. `entries` sono le voci che contano come invii, già filtrate da chi chiama; `seconds` sostituisce
    il setting.
  - `ensure_cooldown(entries, object_id, seconds=None) -> None`: solleva `TooManyRequests(retry_at)` (429) dentro
    l'intervallo.
- **Limite di frequenza** ✅: `rate_limit_until(entries, limit, window_seconds) -> datetime | None`: al massimo `limit`
  azioni in qualunque finestra di `window_seconds`, contando le voci del registro già filtrate da chi chiama (es. le
  `CREATE` degli account creati da uno stesso client, con la chiave di `clients.client_key` nelle `changes`).
  Restituisce quando la voce più vecchia che conta esce dalla finestra, `None` se l'azione è permessa ora. Anche qui
  nessuna tabella propria.

  ```python
  with transaction.atomic():
      Customer.objects.select_for_update().get(pk=customer.pk)
      notified = OrderLog.objects.filter(model="Customer", action=AuditAction.NOTIFY)
      ensure_cooldown(notified, customer.pk)        # 429 se l'ultimo invio è di meno di 60 s fa
      send_email([customer.email], subject, body)
      log_write(OrderLog, request.user, AuditAction.NOTIFY, customer)
  ```
  - Un utente anonimo viene salvato come `actor=None`.
  - `object_label` viene troncato alla lunghezza del campo.
  - `context` contiene i campi aggiuntivi del modello concreto.
- `snapshot(obj, fields=None) -> dict`: restituisce `{attname: valore}` dei campi concreti, in forma
  serializzabile in JSON.
  - Le foreign key compaiono come `"<nome>_id"`.
  - Sono esclusi la chiave primaria e i campi di `DJKIT_AUDIT_EXCLUDED_FIELDS`.
  - `fields` limita il risultato a dei nomi (accetta sia il nome sia l'attname).
- `diff(before, after) -> dict`: `{"campo": [vecchio, nuovo]}` per le sole chiavi cambiate. Una chiave assente
  da un lato conta come `None`.
- `mask_changes(changes: dict) -> dict`: copia di una `snapshot` o di un `diff` con i valori dei campi di
  `DJKIT_AUDIT_MASKED_FIELDS` sostituiti dal testo della chiave `audit_masked` (in un `diff`, entrambi i valori).
  Un valore vuoto (`None` o `""`) resta com'è. Le altre chiavi restano invariate. `log_write` la applica sempre:
  i chiamanti passano `snapshot` e `diff` veri (un `diff` calcolato su valori già mascherati perderebbe le modifiche).
- `mask_value(value)`: il valore mascherato di un campo (vuoto → invariato). `masked_fields()`: il setting.
- `to_json_value(value)`: converte un valore in uno serializzabile in JSON.
  - `Decimal` → stringa, così non si perde precisione.
  - Date e orari → ISO; `UUID` → stringa; istanza di un modello → la sua chiave.
  - I contenitori (liste, tuple, set, dizionari) vengono convertiti elemento per elemento.

### 4.4 `updates` — Modifica parziale ✅

- `apply_patch(obj, data: dict, allowed: set[str] | None = None) -> dict`:
  1. Controlla i campi. Un campo inesistente, non concreto, la chiave primaria o un campo fuori da `allowed`
     sollevano `InvalidData(errors={campo: [messaggio della chiave field_not_editable]})`.
  2. Assegna a `obj` solo i campi in `data`, cioè `payload.dict(exclude_unset=True)`. Per una foreign key
     il valore può essere l'istanza o la sua chiave.
  3. Esegue `full_clean()`, che controlla validatori, choices, unicità e `clean()` del modello. Un errore
     solleva `InvalidData` e non salva nulla.
  4. Salva solo i campi cambiati, con `save(update_fields=...)`.
  5. Restituisce il `diff` dei soli campi salvati (senza i campi esclusi dal registro), pronto per
     `log_write`. Restituisce `{}` se non è cambiato nulla. Un valore uguale a quello salvato ma scritto in
     un altro modo (`Decimal("650")` per un 650.00 salvato) non conta come modifica.

### 4.5 `access` — Permessi: chi legge e chi modifica ✅

Una sola *policy* decide tutto. Il progetto scrive le sue regole in una sottoclasse di `AccessPolicy` e la indica
nell'impostazione `DJKIT_ACCESS_POLICY` (percorso puntato); service ed endpoint non scrivono mai filtri d'accesso,
chiedono solo `scope` / `check` / `get_accessible_or_404`.

- **principal**: chi agisce (oggi un utente; il progetto può passare qualsiasi cosa la sua policy capisca: un
  cliente da un'app, un ruolo, un job automatico).
- `Action` (`TextChoices`): `READ` (vedere: elenchi, dettaglio, resoconti), `WRITE` (creare, modificare, eliminare).
- `AccessLevel` (`TextChoices`): `FULL` (legge e scrive), `READ_ONLY` (solo legge); da mostrare nelle uscite.
- Regole: una riga fuori da `scope(READ)` non esiste per il principal → `NotFound` (non si rivela che esiste);
  una riga dentro `scope(READ)` ma fuori da `scope(WRITE)` è in sola lettura → `Forbidden` (403, `read_only`).
- `class AccessPolicy`:
  - `scope(principal, queryset, action, include_deleted=False) -> QuerySet`: le righe accessibili per l'azione.
    Di default `READ` e `WRITE` danno `queryset.accessible_by(principal)` (vedi `db.AccessibleQuerySet`;
    `include_deleted` solo su un `db.SoftDeleteQuerySet`). Una sottoclasse lo ridefinisce, per esempio per
    dare in lettura anche righe che non si possono modificare.
  - `level(principal, obj, source=None) -> AccessLevel | None`: `FULL`, `READ_ONLY` o `None` (non la vede);
    `source` (modello, manager o QuerySet) dice dove cercare la riga, di default il manager del modello.
- `get_policy() -> AccessPolicy`: la policy di `DJKIT_ACCESS_POLICY` (istanza in cache), o `AccessPolicy()`.
- `scope(principal, source, action=Action.READ, include_deleted=False) -> QuerySet`: `get_policy().scope(...)`;
  `source` è un modello, un manager o un QuerySet (che mantiene i suoi filtri).
- `level(principal, obj, source=None)`: `get_policy().level(...)`.
- `check(principal, action, obj, detail=None, read_only_detail=None, source=None)`: `NotFound(detail)` se non la vede,
  `Forbidden(read_only_detail)` se l'azione è `WRITE` e la riga è in sola lettura.
- `get_accessible_or_404(source, user, pk, *, action=Action.READ, for_update=False, include_deleted=False,
  detail=None, read_only_detail=None)`: carica una riga per chiave tra quelle di `scope(user, source, READ)`,
  oppure solleva `NotFound(detail)`; con `action=WRITE` una riga solo leggibile dà `Forbidden(read_only_detail)`.
  - Con `include_deleted=True` trova anche le righe eliminate logicamente (serve un `db.SoftDeleteQuerySet`):
    si usa per la consultazione; prima di una modifica va seguita da `db.ensure_not_deleted`.
  - Anche una chiave malformata (per esempio `"abc"` per un intero) dà `NotFound`, mai un errore 500.
  - Con `for_update` usa `select_for_update()`: va chiamata dentro `transaction.atomic()`.
  - **Prima di una modifica passare sempre `action=Action.WRITE`**: con il default `READ` una policy che dà
    righe in sola lettura le restituirebbe anche a chi non può modificarle.

```python
# settings.py
DJKIT_ACCESS_POLICY = "billing.access.BillingPolicy"

# billing/access.py
class BillingPolicy(AccessPolicy):
    def scope(self, principal, queryset, action, include_deleted=False):
        mine = super().scope(principal, queryset, action, include_deleted)
        if action == Action.WRITE:
            return mine
        return queryset.filter(Q(pk__in=mine.values("pk")) | Q(auditors=principal))  # i revisori leggono

# un service
invoice = get_accessible_or_404(Invoice, user, pk, action=Action.WRITE, for_update=True)
```

### 4.5a `workspaces` — Spazi di lavoro separati ✅

Più insiemi di dati separati nello stesso database (multi-tenancy a righe): ogni utente appartiene a uno o più
*spazi di lavoro* con un ruolo; uno è quello **attivo**, e le regole di accesso del progetto (§4.5) limitano ogni
query a quello. Un ruolo (di default `"ADMIN"`) è l'amministratore dello spazio: al massimo uno per spazio.

**Contratto con il progetto:**
- un modello concreto dello spazio, sottoclasse di `WorkspaceModel` (astratto, `SoftDeleteModel` +
  `created_at`): uno spazio chiuso resta come riga eliminata logicamente finché il progetto non lo cancella;
- un modello concreto dell'appartenenza, sottoclasse di `MembershipModel` (astratto, `SoftDeleteModel` + `role`,
  `joined_at`), con le FK `user` e `workspace` entrambe con `related_name="memberships"`; nel `Meta` può usare
  `MembershipModel.one_admin_constraint(name)` (un solo amministratore vivo per spazio) e
  `MembershipModel.one_membership_constraint(name)` (una sola appartenenza viva per utente e spazio);
- il modello utente ha `current_workspace` (FK nullable allo spazio): l'ultimo scelto, ricordato tra le sessioni.

- facoltativo: un modello concreto dell'invito, sottoclasse di `InvitationModel` (astratto: `email`,
  `token_digest` unico, `created_at`, `sent_at`, `expires_at`, `accepted_at`, `revoked_at`), con le FK che servono
  al progetto. Il link inviato porta un token casuale; nel database c'è solo il suo SHA-256, così una copia del
  database non dà link validi.

**Impostazioni:** `DJKIT_WORKSPACE_ADMIN_ROLE` (default `"ADMIN"`), `DJKIT_INVITATION_VALID_DAYS` (default 7).

**Funzioni:**
- `memberships(user) -> QuerySet`: appartenenze vive di spazi vivi, dalla più vecchia (spazio caricato).
- `active_membership(user)`: quella di `current_workspace` se dà ancora accesso, altrimenti quella da
  amministratore, altrimenti la più vecchia; `None` senza spazi o per un utente anonimo. Memorizzata
  sull'istanza dell'utente (vive una richiesta).
- `active_workspace(user)`, `is_workspace_admin(user) -> bool`.
- `switch_workspace(user, workspace_id)`: rende attivo un altro spazio dell'utente e salva `current_workspace`;
  `NotFound` (messaggio `workspace_not_found`) se l'utente non ne fa parte.
- `acting_in(user, membership)`: context manager per agire in un'appartenenza data e poi tornare a quella di
  prima (lavori programmati che servono ogni spazio di un utente).
- `forget_active(user)`: dimentica l'appartenenza memorizzata (dopo averla cambiata).
- `leave(membership, when=None)`: chiude un'appartenenza (eliminazione logica) e azzera `current_workspace`
  dell'utente se puntava lì.
- Inviti: `InvitationModel.OPEN_Q` (né accettato né revocato), `is_open(now)` (anche non scaduto),
  `renew(now)` (nuovo token e nuova validità, il link di prima smette di valere; non salva; restituisce il token);
  `new_invitation_token() -> (token, digest)`, `token_digest(token)`,
  `find_open_invitation(queryset, token, now=None, for_update=False)`: l'invito aperto del token, altrimenti
  `NotFound` (`invitation_not_found`) — la stessa risposta per token sconosciuto, usato, revocato o scaduto.

```python
# models.py del progetto
class Team(WorkspaceModel): ...
class Membership(MembershipModel):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="memberships")
    workspace = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="memberships")
    class Meta:
        constraints = [MembershipModel.one_admin_constraint("membership_one_admin")]

# policy del progetto: tutto dentro lo spazio attivo, l'amministratore vede tutto
def scope(self, principal, queryset, action, include_deleted=False):
    team = active_workspace(principal)
    if team is None:
        return queryset.none()
    rows = queryset.filter(team=team)
    return rows if is_workspace_admin(principal) else super().scope(principal, rows, action, include_deleted)
```

### 4.5c `retention` — Conservazione dei dati eliminati ✅

Quanto restano le righe chiuse o eliminate prima che il progetto le cancelli definitivamente, e quando avvisare
il proprietario. Il modulo calcola solo le date; cosa cancellare e come lo decide il progetto.

**Impostazioni:** `DJKIT_RETENTION_DAYS` (default 183, positivo), `DJKIT_RETENTION_WARNING_DAYS` (default 30,
da 0 a `DJKIT_RETENTION_DAYS - 1`); valori fuori dai limiti → `ImproperlyConfigured`.

**Funzioni:** `retention_days()`, `warning_days()`, `purge_at(deleted_at)` (quando viene cancellata una riga
eliminata in quel momento), `purge_cutoff(now=None)` (le righe eliminate fino a lì sono da cancellare),
`warning_cutoff(now=None)` (le righe eliminate fino a lì ricevono l'avviso).

### 4.5b `fields` — Campi e vincoli ✅

- `choice_field(verbose_name, choices, max_length=DEFAULT_CHOICE_LENGTH, **kwargs) -> CharField`: campo
  `VARCHAR` limitato a una classe `TextChoices` (`DEFAULT_CHOICE_LENGTH = 12`).
- `choices_constraint(field, values, name) -> CheckConstraint`: `CHECK field IN (values)`. Django non crea
  questo vincolo da solo.
- `money_field(verbose_name, max_digits=10, decimal_places=2, **kwargs) -> DecimalField`: importi in `Decimal`,
  mai in `float`.
- `positive_constraint(field, name) -> CheckConstraint`: `CHECK field > 0`.
- I nomi dei vincoli possono usare `%(app_label)s` e `%(class)s`.

### 4.6 `db` — Helper per le query ✅

- `AccessibleQuerySet`: QuerySet base. Il modello dichiara `ACCESS_PATH`, il lookup dalla riga agli utenti che
  possono vederla (per esempio `"members"` oppure `"team__members"`).

```python
class Invoice(models.Model):
    ACCESS_PATH = "team__members"
    objects = AccessibleQuerySet.as_manager()

Invoice.objects.accessible_by(request.user)
```
  - `accessible_by(user)`: filtra le righe accessibili all'utente (isolamento dei dati tra gruppi).
  - `ACCESS_CONDITIONS` (facoltativo, dizionario di lookup): condizioni aggiunte **nella stessa** `filter()` di
    `ACCESS_PATH`, quindi su una relazione multipla controllano la **stessa** riga collegata (l'appartenenza che dà
    l'accesso). Esempio: accesso solo tramite appartenenze non eliminate:

```python
class Project(models.Model):
    ACCESS_PATH = "team__memberships__user"
    ACCESS_CONDITIONS = {"team__memberships__is_deleted": False}
```
  - `_model(name)`: restituisce un altro modello della **stessa app** del modello, senza import circolari.
- `SoftDeleteModel`: modello astratto per l'**eliminazione logica**. Aggiunge `is_deleted` (`BooleanField`,
  default `False`) e `deleted_at` (`DateTimeField`, vuoto finché la riga non è eliminata): eliminare una riga vuol
  dire segnarla, non cancellarla, così le FK che la puntano restano valide e lo storico resta **consultabile**.
  Il manager di default restituisce **tutte** le righe (admin, oggetti collegati, storico). Una riga eliminata è in
  sola lettura (`ensure_not_deleted`).
  - `deleted_state_constraint(name) -> CheckConstraint` (statico): vincolo del database che tiene coerenti i due
    campi (eliminata ⇔ `deleted_at` valorizzato); va messo nei `Meta.constraints` del modello concreto.
  - `mark_deleted(when=None)`: elimina logicamente la riga e salva solo i due campi; `when` è l'ora
    dell'eliminazione (default: adesso), da passare uguale a tutte le righe eliminate dalla stessa operazione.
- `SoftDeleteQuerySet(AccessibleQuerySet)`: QuerySet da usare con `SoftDeleteModel`.
  - `alive()`: le righe non eliminate; `deleted()`: quelle eliminate.
  - `filter_deleted(mode)`: applica un `DeletedFilter` (`ValueError` se il valore è sconosciuto).
  - `accessible_by(user, include_deleted: bool = False)`: come in `AccessibleQuerySet`, ma **nasconde le righe
    eliminate**; `include_deleted=True` le restituisce (consultazione, da combinare con `filter_deleted`). Senza,
    `access.get_accessible_or_404` risponde `NotFound` su una riga eliminata, come se non esistesse.
  - `mark_deleted(when=None) -> int`: elimina logicamente le righe con un solo `UPDATE` (niente `save()` né
    segnali) e restituisce quante non erano ancora eliminate; quelle già eliminate tengono il loro `deleted_at`.
  - I vincoli che devono ignorare le righe eliminate (unicità, esclusione) vanno dichiarati con
    `condition=Q(is_deleted=False)`.
- `DeletedFilter` (`TextChoices`): quali righe restituisce un elenco rispetto all'eliminazione logica:
  `exclude` (solo le non eliminate, il default dell'interfaccia), `include` (tutte), `only` (solo le eliminate).
  Si usa come tipo di un parametro di query: un valore non ammesso dà 422 (messaggio della chiave `choice`).
- `ensure_not_deleted(obj, detail=None) -> None`: se la riga è eliminata solleva `Conflict(detail)` (409), con il
  messaggio della chiave `deleted_read_only` se `detail` manca. Si chiama prima di ogni modifica di una riga che il
  client può vedere anche da eliminata: 409 spiega il motivo meglio di un 404.

```python
class Customer(SoftDeleteModel):
    ACCESS_PATH = "team__members"
    objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        constraints = [SoftDeleteModel.deleted_state_constraint("customer_deleted_state")]

@router.get("/customers")
def list_customers(request, deleted: DeletedFilter = DeletedFilter.EXCLUDE):
    return Customer.objects.accessible_by(request.user, include_deleted=True).filter_deleted(deleted)

customer = get_accessible_or_404(Customer, user, pk, for_update=True, include_deleted=True)
ensure_not_deleted(customer)                          # 409 se eliminato
customer.mark_deleted()                               # eliminazione logica
```
- `sum_subquery(queryset, field: str = "amount", max_digits: int = 14, decimal_places: int = 2) -> Coalesce`:
  subquery correlata con la somma di un campo, come `DecimalField(max_digits, decimal_places)`. Se non ci sono
  righe restituisce 0 con `decimal_places` decimali (`Decimal("0.00")`). Si usa in `annotate()`.
- `count_subquery(queryset) -> Coalesce`: subquery correlata con il numero di righe, 0 se non ce ne sono.
- `date_filter(field: str, as_of: date | Expression | OuterRef | None) -> Q`: restituisce `Q(field__lte=as_of)`,
  oppure `Q()` vuoto se `as_of` è `None`. `as_of` può essere un'espressione, per una data che cambia da riga a riga
  (es. `OuterRef("reference_date")` dentro una subquery correlata).
- `ensure_unique(source, values: dict, exclude_pk=None, messages: dict | None = None) -> None`: `source` è la classe
  del modello (si cercano tutte le righe) o un QuerySet, quando i valori devono essere unici solo in un sottoinsieme
  (es. un vincolo unico parziale: solo le righe attive). Controlla ogni campo
  di `values` (già normalizzato; i `None` sono saltati) e, se un'altra riga usa già quel valore, solleva
  `Conflict(errors={campo: [messaggio]})` con tutti i campi occupati; `detail` unisce i messaggi distinti.
  `exclude_pk` esclude la riga in modifica; `messages` (`{campo: testo}`) sostituisce, per i campi indicati, il
  messaggio generico della chiave `unique`. Si chiama prima di salvare, per rispondere 409 invece di 422.

```python
ensure_unique(Customer, {"email": email, "vat_number": vat}, exclude_pk=customer.pk)
ensure_unique(Customer.objects.filter(is_active=True), {"email": email})  # unico solo tra i clienti attivi
```

### 4.7 `dates` — Date mensili e annuali ✅

Funzioni pure, senza database.

- `clamped_date(year, month, day) -> date`: costruisce la data, riportando `day` all'ultimo giorno del mese
  se il mese è più corto (31 aprile → 30 aprile).
- `add_months(year, month, months) -> tuple[int, int]`: sposta `(anno, mese)` in avanti di `months` mesi,
  gestendo il cambio d'anno.
- `monthly_due_dates(start_date, end_date) -> list[date]`: la prima scadenza è `start_date`, poi lo stesso giorno
  di ogni mese (adattato alla lunghezza del mese, senza "slittare": 31/1 → 28/2 → 31/3), fino a `end_date`
  incluso. Lista vuota se `end_date < start_date`.
- `yearly_anniversaries(origin, start, end) -> list[date]`: gli anniversari di `origin` (uno, due… anni dopo; non
  `origin` stessa) compresi tra `start` e `end` inclusi, in ordine. Un 29 febbraio cade il 28 negli anni non
  bisestili. Lista vuota se `end < start`.

### 4.7a `deadlines` — Registro delle scadenze ✅

Un solo punto in cui un progetto raccoglie ogni tipo di scadenza (pagamenti, rinnovi, fine di un contratto…), per
una pagina calendario e per le notifiche: leggendo tutti e due lo stesso registro, non possono dare risultati
diversi. Un nuovo tipo si aggiunge registrando un provider, senza toccare chi chiama `collect`.

- `Deadline` (dataclass immutabile): `kind` (codice del tipo, in inglese), `due_date`, `subject` (codice di ciò a cui
  si riferisce, es. `"invoice"`), `subject_id`, `amount: Decimal | None = None`, `context: dict` (dati extra
  serializzabili in JSON per l'interfaccia).
- `DeadlineRegistry()`:
  - `provider(kind)` → decoratore che registra la funzione `(user, start, end) -> Iterable[Deadline]` del tipo; un
    secondo provider per lo stesso tipo → `ValueError`;
  - `kinds() -> list[str]`: i tipi registrati, ordinati;
  - `collect(user, start, end, kinds=None) -> list[Deadline]`: le scadenze di tutti i provider (o solo di `kinds`)
    ordinate per data, tipo e id. `end < start` o un tipo sconosciuto → `ValueError`; un provider che restituisce
    una scadenza di un altro tipo o fuori dal periodo → `ValueError` (è un suo bug). Le regole d'accesso le applica
    ogni provider.

```python
registry = DeadlineRegistry()

@registry.provider("invoice_due")
def invoices_due(user, start, end):
    return [Deadline("invoice_due", i.due_date, "invoice", i.pk, amount=i.total)
            for i in Invoice.objects.accessible_by(user).filter(due_date__range=(start, end))]

registry.collect(user, date(2026, 6, 1), date(2026, 6, 30))
```

- `urgency(due_date, today, levels, overdue) -> str | None`: quanto è vicina una scadenza, come codice scelto dal
  progetto (es. per colorarla). `levels` sono coppie `(giorni, codice)`: vince il livello con meno giorni tale che
  `due_date <= today + giorni`; una scadenza già passata riceve `overdue`; oltre tutti i livelli → `None`. Giorni
  negativi o ripetuti → `ValueError`.

```python
urgency(date(2026, 6, 15), date(2026, 6, 10), [(7, "this_week"), (30, "this_month")], overdue="overdue")
# -> "this_week"
```

### 4.7b `notices` — Avvisi delle scadenze ✅

Avvisare ogni utente, per email, delle scadenze dei prossimi giorni lette da un `DeadlineRegistry`, con preferenze
per utente e senza ripetere ciò che è già stato avvisato. Il progetto scrive i modelli concreti, l'email e il job.

- `NoticeRule(enabled, days_before)` (dataclass immutabile): avvisare o no un tipo, e con quanti giorni di anticipo
  (la finestra va da oggi a oggi + `days_before`; 0 = solo le scadenze di oggi). `MAX_DAYS_BEFORE = 366`.
- `rules(defaults, saved) -> dict[str, NoticeRule]`: le regole in vigore, i default del progetto sostituiti da ciò che
  l'utente ha salvato (`(kind, enabled, days_before)`); i tipi che non sono tra i default si ignorano.
- `deadline_key(deadline) -> (kind, subject, subject_id)`: ciò che identifica una scadenza nel tempo (non la data, che
  può spostarsi o tornare ogni anno).
- `to_notify(registry, user, today, rules, sent) -> list[Deadline]`: le scadenze dell'avviso di oggi: ogni tipo attivo
  nella sua finestra, tolte quelle già avvisate per la stessa data (`sent`: `{deadline_key: data avvisata}`); una
  data nuova della stessa scadenza (un rinnovo annuale, una scadenza spostata) si avvisa di nuovo.
- `sent_for(model, user)`, `record(model, user, deadlines, when)` (una riga per scadenza, **sovrascritta** se esiste
  già), `prune(model, today) -> int` (cancella le righe di scadenze già passate: la tabella tiene solo quelle delle
  finestre di avviso).
- Modelli astratti (FK all'utente `PROTECT`):
  - `NoticePreferenceBase`: `user`, `kind`, `enabled`, `days_before`; unico (`user`, `kind`), vincolo
    `"<app>_<class>_unique_kind"` (`unique_constraint(name)` per chi ridefinisce `Meta.constraints`);
  - `DeadlineNoticeBase`: `user`, `kind`, `subject`, `subject_id`, `due_date`, `notified_at`; unico (`user`, `kind`,
    `subject`, `subject_id`), vincolo `"<app>_<class>_unique_deadline"` (`unique_constraint(name)`).

```python
prune(DeadlineNotice, today)
for user in recipients:
    found = to_notify(registry, user, today, rules(DEFAULTS, saved_of(user)), sent_for(DeadlineNotice, user))
    if found:
        send_summary(user, found)
        record(DeadlineNotice, user, found, timezone.now())
```

### 4.8 `validators` e `it` — Dati personali e formati italiani ✅

- `validators.normalize_email_address(value: str | None) -> str | None`: toglie gli spazi e converte in minuscolo.
- `validators.strip_text_values(data: dict) -> dict`: copia di `data` con gli spazi tolti attorno a ogni valore
  di testo, prima della validazione del modello: `"   "` diventa `""` e viene rifiutato da un campo obbligatorio.
  `None` resta `None`.
- `it.TAX_CODE_LENGTH = 16`
- `it.validate_tax_code`: istanza di `it.TaxCodeValidator` (deconstructible, nessuna opzione) che accetta
  esattamente 16 lettere maiuscole o cifre (`TAX_CODE_PATTERN`), oppure da 1 a 16 con `dev.relaxed_validation()`
  attivo (`RELAXED_TAX_CODE_PATTERN`); codice `invalid_tax_code`. Non controlla il carattere finale. Il messaggio è la chiave `tax_code_invalid` (`{length}`), letta quando viene mostrato.
- `it.normalize_tax_code(value: str | None) -> str | None`: toglie gli spazi e converte in maiuscolo.
- Formati dei valori dentro i testi in italiano (un frontend che formatta con `Intl` in `it-IT` ottiene lo stesso
  risultato):
  - `it.format_date(value: date) -> str`: `"15/03/2026"`.
  - `it.format_amount(value: Decimal) -> str`: `"1.234,50"` (senza simbolo).
  - `it.format_percent(value: Decimal) -> str`: `"50"`, `"33,33"` (senza simbolo e senza zeri inutili).
  - `it.format_names(names) -> str`: `"Anna"`, `"Anna e Bruno"`, `"Anna, Bruno e Carla"`.

### 4.8a `dev` — Validazione allentata in sviluppo ✅

- `relaxed_validation() -> bool`: valore di `DJKIT_RELAXED_VALIDATION` (default `False`). Attivo con `DEBUG`
  spento → `ImproperlyConfigured`: non deve mai arrivare in produzione.
- Salta solo i controlli che rallentano l'inserimento dei dati di prova; restano tutte le regole da cui dipende la
  logica (unicità, coerenza di importi e date, conferme). In `djkit` allenta `auth.validate_new_password`
  (nessun validatore) e `it.validate_tax_code` (da 1 a 16 caratteri).
- `testing.runner.VerboseTestRunner` lo spegne durante i test.

```python
# settings.py
DJKIT_RELAXED_VALIDATION = env_bool("DEV_RELAXED_VALIDATION", default=False)
```

### 4.9 `mail` — Invio email ✅

Nessuna libreria esterna: usa `django.core.mail`. Il server lo sceglie `EMAIL_BACKEND` di Django (per esempio console
in sviluppo, SMTP in produzione; nei test Django usa la memoria e le email finiscono in `mail.outbox`).

- `render_email(template_name: str, context: dict) -> tuple[str, str]`: `(oggetto, testo)` dai template
  `"<template_name>_subject.txt"` e `"<template_name>_body.txt"`, così i testi (e la loro lingua) stanno nel progetto.
  L'oggetto viene ridotto a una riga. I template sono testo semplice: per non trasformare `&` in `&amp;` (es. nei
  link) il testo va racchiuso in `{% autoescape off %}…{% endautoescape %}`.
- `send_email(to: list[str], subject: str, body: str, *, reply_to: list[str] | None = None, from_email: str | None = None) -> bool`:
  invia un'email di testo con `EmailMessage` (mittente `DEFAULT_FROM_EMAIL` se `from_email` manca). `True` se
  l'email è stata consegnata al backend, `False` in modalità demo (`DJKIT_MAIL_DEMO_MODE`: l'email viene solo
  registrata nel log, con destinatari e oggetto). Gli errori del server **non** vengono nascosti
  (`fail_silently=False`): arrivano al chiamante, che decide cosa mostrare all'utente.
- `demo_mode() -> bool`: il setting `DJKIT_MAIL_DEMO_MODE`.
- **Domini bloccati** ✅: `send_email` non scrive mai agli indirizzi dei domini di `DJKIT_MAIL_BLOCKED_DOMAINS` (anche
  ai loro sottodomini). Di default sono i domini riservati agli esempi e ai test (`RESERVED_DOMAINS`, RFC 2606 e RFC
  6761: `example.com`, `example.net`, `example.org`, `example`, `invalid`, `test`, `localhost`), così i dati di
  esempio non fanno mai partire un'email. Gli indirizzi bloccati vengono tolti dai destinatari e scritti nel log; se
  non resta nessuno l'email non parte e `send_email` restituisce `False`. `[]` spegne il controllo.
  - `blocked_domains() -> tuple[str, ...]`: i domini dal setting.
  - `is_blocked(address) -> bool`: se l'indirizzo è in un dominio bloccato.
- `ReadableConsoleBackend`: backend email per lo sviluppo (`EMAIL_BACKEND = "djkit.mail.ReadableConsoleBackend"`).
  Stampa nel terminale `From`, `To`, `Cc`, `Reply-To`, `Subject` e il testo **così com'è scritto**. Il backend console
  di Django stampa invece il messaggio codificato: con lettere accentate il testo diventa quoted-printable e nei link
  compaiono `=3D` e righe spezzate, che non si possono copiare.

```python
subject, body = render_email("shop/emails/welcome", {"user": user})
send_email([user.email], subject, body, reply_to=[shop.owner_email])
```

### 4.9c `clients` — Chi sta chiamando ✅

Per i limiti anti-abuso degli endpoint pubblici.

- `client_address(request, proxy_count=0) -> str`: l'indirizzo del client. Con `proxy_count = 0` è `REMOTE_ADDR`;
  dietro `proxy_count` reverse proxy che aggiungono l'indirizzo ricevuto a `X-Forwarded-For` è il `proxy_count`-esimo
  indirizzo da destra (quelli a sinistra li può scrivere il client); `REMOTE_ADDR` se l'intestazione è più corta.
- `client_key(request, proxy_count=0) -> str`: un hash con chiave (`salted_hmac` con `SECRET_KEY`) di quell'indirizzo,
  32 caratteri esadecimali: stabile per lo stesso client, inutile per identificare una persona, quindi si può scrivere
  nel registro.

```python
key = client_key(request, proxy_count=1)
until = rate_limit_until(Entry.objects.filter(changes__client=key), limit=3, window_seconds=3600)
if until is not None:
    raise TooManyRequests(until)
```

### 4.9a `texts` — Catalogo dei testi ✅

Per i progetti che vogliono **tutti** i testi dell'interfaccia (messaggi dell'API, etichette dei valori, testi delle
pagine del frontend) in un unico posto, usati solo per chiave. I messaggi propri di `djkit` restano in `messages`.

- `TextCatalog(data: dict)`: catalogo annidato con chiavi a punti. Ogni foglia è un testo oppure un plurale
  `{"one": "...", "other": "..."}`; qualunque altra foglia (numero, gruppo vuoto) → `TypeError` quando il catalogo
  viene creato.
  - `text(key, **params) -> str`: il testo con i segnaposto `{nome}` riempiti. Un plurale sceglie la forma con
    `count` (1 → `one`, altrimenti `other`). Chiave inesistente → `UnknownTextKey`; segnaposto senza valore (o
    plurale senza `count`) → `MissingTextParameter`. Mai un testo vuoto.
  - `keys(sections=None) -> list[str]`: tutte le chiavi, ordinate (per i test di completezza e per i tipi).
  - `section(name) -> dict`, `public_data(sections=None) -> dict`: le sezioni per il frontend più `version`, un hash
    breve del contenuto.
- `catalog_response(request, data) -> HttpResponse`: JSON con `ETag` e `Cache-Control: no-cache`; con un
  `If-None-Match` uguale risponde 304 senza corpo.
- `typescript_keys(catalog, sections=None) -> str`: modulo TypeScript con `type TextKey` (unione delle chiavi) e
  `TEXT_KEYS`, così un frontend che usa una chiave inesistente non compila.
- `project_catalog()`, `public_sections()`, `content_hash(data)`, `placeholders(text)`, `is_plural(value)`.
- Comando `manage.py export_text_types [--output file.ts]`: scrive (o stampa) il modulo di `typescript_keys`.
- Setting: `DJKIT_TEXT_CATALOG` (percorso dell'istanza `TextCatalog` del progetto), `DJKIT_TEXT_PUBLIC_SECTIONS`
  (sezioni inviate al frontend ed esportate, default `["ui", "value"]`).

```python
CATALOG = TextCatalog({"api": {"order": {"not_found": "Ordine non trovato."}},
                       "ui": {"cart": {"items": {"one": "{count} articolo", "other": "{count} articoli"}}}})
CATALOG.text("ui.cart.items", count=3)    # "3 articoli"
```

### 4.9b `numbers` — Numeri ✅

- `split_evenly(total: Decimal, parts: int, step: Decimal = CENT) -> list[Decimal]`: divide `total` in `parts` parti
  uguali arrotondate per difetto a `step` (default `Decimal("0.01")`); gli `step` che avanzano vanno uno ciascuno alle
  **prime** parti, così la somma è sempre esattamente `total` e chi riceve i centesimi lo decide il chiamante
  ordinando i propri elementi. Esempio: 100 in 3 → `[33.34, 33.33, 33.33]`. `parts < 1` o `total` non multiplo di
  `step` → `ValueError`.
- `split_by_weights(total: Decimal, weights: Sequence[Decimal], step: Decimal = CENT) -> list[Decimal]`: divide `total`
  (anche negativo) in proporzione ai pesi, con il metodo dei resti più grandi: ogni parte è arrotondata verso zero a
  `step` e gli `step` che avanzano vanno alle parti con il resto scartato più grande (a parità, le prime). La somma è
  sempre esattamente `total`. Esempio: 100 per `[1, 1, 1]` → `[33.34, 33.33, 33.33]`. Nessun peso, un peso negativo,
  pesi tutti 0 o `total` non multiplo di `step` → `ValueError`.
- `round_half_up(value: Decimal, step: Decimal = CENT) -> Decimal`: arrotonda a `step` con le metà verso l'alto (lontano da zero), come i moduli fiscali e le fatture: `103.008` → `103.01`, `0.125` → `0.13`. `Decimal.quantize` da solo arrotonda le metà al pari (`0.125` → `0.12`).
- `minimal_transfers(balances: Mapping[K, Decimal]) -> list[tuple[K, K, Decimal]]`: i trasferimenti `(chi paga, chi
  riceve, importo)` che azzerano dei saldi (> 0 deve ricevere, < 0 deve dare), nel minor numero di passaggi: il
  minimo è *n − g*, con *n* saldi non nulli e *g* il massimo numero di gruppi disgiunti a somma zero; ogni gruppo si
  chiude accoppiando il debitore più grande con il creditore più grande. Esatto fino a `EXACT_TRANSFERS_LIMIT` (12)
  saldi non nulli, oltre approssimato con l'accoppiamento greedy. Saldi che non sommano a zero → `ValueError`.

```python
minimal_transfers({"anna": Decimal("-700"), "bruno": Decimal("700")})
# -> [("anna", "bruno", Decimal("700"))]
```

### 4.9d `pagination` — Liste a pagine ✅

Liste lunghe a pagine per numero di pagina, come le mostra un'interfaccia
("pagina 3, 25 righe per pagina"), con un insieme fisso di dimensioni ed
errori chiari per quello che può essere solo un errore del chiamante.

| Nome | Firma | Descrizione | Stato |
|---|---|---|---|
| `PageNumber` | paginatore di Django Ninja (`@paginate(PageNumber)`) | query `?page=` (da 1, predefinito 1) e `?size=` (una di `DJKIT_PAGE_SIZES`, predefinita `DJKIT_PAGE_SIZE`); risposta `{items, count, page, size, pages}` | ✅ |
| `page_of` | `page_of(rows, page=1, size=None) -> Page` | la stessa pagina per un service o un comando, senza Ninja; `rows` è un QuerySet **ordinato** o una lista | ✅ |
| `Page` | dataclass `items, count, page, size, pages` | una pagina (`pages` almeno 1) | ✅ |
| `page_sizes()`, `default_page_size()` | — | le impostazioni lette a ogni chiamata (`override_settings` funziona); `DJKIT_PAGE_SIZE` fuori da `DJKIT_PAGE_SIZES` → `ValueError` | ✅ |

Errori: dimensione non ammessa → `InvalidData` su `size` (chiave
`page_size_not_allowed`, con `{sizes}`); pagina sotto 1 o dopo l'ultima
(con almeno una riga) → `InvalidData` su `page` (`page_out_of_range`, con
`{pages}`); la pagina 1 di una lista vuota va bene; un QuerySet non
ordinato → `ValueError` (le pagine si sovrapporrebbero o salterebbero
righe).

Impostazioni: `DJKIT_PAGE_SIZES` (predefinito `(10, 25, 50, 100)`),
`DJKIT_PAGE_SIZE` (predefinito 25).

```python
@router.get("", response=list[ItemOut])
@paginate(PageNumber)
def list_items(request):
    return Item.objects.order_by("-created", "pk")
```

### 4.10 `testing.runner` — Output leggibile dei test ✅

- `VerboseTestRunner` (`DiscoverRunner`): stampa una riga per test, raggruppata per modulo e classe.
  Ogni riga riporta esito, nome leggibile, durata, file del progetto eseguiti (rilevati con `sys.monitoring`)
  e, sotto, la prima riga della docstring. Alla fine stampa un riepilogo.
  - `-v 0`: output standard di Django.
  - `-v 2`: aggiunge anche i messaggi di Django.
  - `--debug-sql` e `--pdb`: si usano le classi di Django.
  - Durante i test sostituisce `PASSWORD_HASHERS` con `password_hashers_for_tests()` (in
    `setup_test_environment`, con `override_settings`) e rimette quelli del progetto in
    `teardown_test_environment`. Vale con ogni verbosità.
  - Durante i test forza `DJKIT_RELAXED_VALIDATION = False` (`install_strict_validation`, anche nei processi
    figli di `--parallel`): la suite controlla sempre le regole di produzione.
  - `--parallel N`: `parallel_test_suite = VerboseParallelTestSuite`. Ogni processo figlio installa anche lui gli
    hasher veloci (`_init_worker_with_test_hashers`: con `spawn` / `forkserver`, il default da Python 3.14, il figlio
    non eredita la sostituzione del processo principale) e registra i file eseguiti da ogni test
    (`TrackingRemoteTestResult`), che arrivano al processo principale con l'evento `addSourceFiles` prima di
    `stopTest`. Le righe escono una classe di test alla volta, man mano che i processi le finiscono. Per vedere i
    traceback dei test falliti in parallelo serve il pacchetto `tblib` (senza, Django non riesce a trasmetterli).
- `install_test_password_hashers() -> override_settings | None`: sostituisce `PASSWORD_HASHERS` con
  `password_hashers_for_tests()` e salva quelli del progetto per `project_password_hashers()`; restituisce l'override
  attivo (o `None` se il setting è `None`). Lo usano il runner e i processi figli.
- `DEFAULT_TEST_PASSWORD_HASHERS`: `("django.contrib.auth.hashers.MD5PasswordHasher",)`, un hash veloce. Le password
  di test non sono segrete; i hasher di produzione sono lenti apposta e ogni utente creato nei test ne pagherebbe il
  costo.
- `password_hashers_for_tests() -> list[str] | None`: `DJKIT_TEST_PASSWORD_HASHERS` (o
  `DEFAULT_TEST_PASSWORD_HASHERS`) come lista; `None` se il setting è `None`.
- `project_password_hashers() -> list[str]`: i `PASSWORD_HASHERS` veri del progetto, anche mentre il runner ha
  installato quelli di test. Serve ai pochi test che verificano come vengono salvate le password in produzione:
  `with override_settings(PASSWORD_HASHERS=project_password_hashers()): ...`. Anche `check_password` va chiamato
  dentro il blocco, perché riconosce solo gli algoritmi elencati in `PASSWORD_HASHERS`.
- `project_source(filename, root, skip_dirs, skip_files, skip_tree=TESTING_PACKAGE_DIR) -> str | None`: decide se un
  file è codice del progetto sotto test e restituisce il percorso relativo a `root`. Restituisce `None` in questi casi:
  il file è fuori da `root`, non è un `.py`, il suo nome inizia con `test`, ha un nome in `skip_files`, sta in una
  cartella di `skip_dirs`, oppure sta dentro `skip_tree` (il pacchetto `djkit.testing`, sempre escluso).
- `excluded_dirs() -> frozenset[str]`: `DJKIT_TEST_EXCLUDED_DIRS` (o `DEFAULT_EXCLUDED_DIRS`) più le cartelle del
  modulo settings.
- `excluded_files() -> frozenset[str]`: `DJKIT_TEST_EXCLUDED_FILES` (o `DEFAULT_EXCLUDED_FILES`).
- `readable_name(method_name) -> str`: `"test_as_of_day"` → `"as of day"`. Toglie un solo prefisso `test_`.
- `first_doc_line(obj) -> str`: prima riga non vuota della docstring, `""` se non c'è.

### 4.11 `testing.api` — Helper per i test delle API ✅

- `ApiClient` (`django.test.Client`): client di test per API JSON protette da sessione.
  - Il controllo CSRF è attivo come in un browser vero: il client salva un cookie CSRF e lo copia
    nell'header di ogni richiesta. Con `ApiClient(send_csrf_token=False)` l'header non viene inviato, per
    verificare che la richiesta venga rifiutata (403).
  - `post`, `put`, `patch` e `delete` inviano `data` come JSON, a meno che si indichi un altro `content_type`.
- `make_user(password=DEFAULT_PASSWORD, **overrides)`: crea un utente del modello utente del progetto.
  - Riempie `USERNAME_FIELD` e `REQUIRED_FIELDS` con valori segnaposto unici: `user<n>@example.com` per le
    email, `user<n>` per gli altri campi, tagliati a `max_length`.
  - Se il modello ha regole più rigide, si passano `overrides` oppure si usano le factory del progetto.
- `ApiTestCase` (`TestCase`, con `client_class = ApiClient`):
  - `client_for(user=None, *, send_csrf_token=True) -> ApiClient`: restituisce un client nuovo, già loggato
    se `user` è indicato.
  - `assertStatus(response, status)`: se lo status è diverso, il messaggio di errore mostra il corpo
    della risposta.
  - `assertNotAccessible(client, method, path, data=None)`: verifica che il percorso corrisponda a una rotta vera (un indirizzo che non esiste più risponderebbe 404 anche lui, pure tramite la rotta di riserva `views.page_not_found`, e il test passerebbe senza controllare niente) e che la risposta sia 404 e mai 403,
    per i test di isolamento.

---

## 5. Da cartella a pacchetto installabile

Se `djkit` è incluso come cartella dentro un progetto, per renderlo un pacchetto:

1. Sposta la cartella `djkit/` in un repository a parte e aggiungi un `pyproject.toml` con nome `djkit`,
   versione uguale a `__version__` e dipendenze `Django` e `django-ninja`.
2. Crea il tag `vX.Y.Z` e installa con `pip install git+https://github.com/<utente>/djkit@vX.Y.Z`
   (oppure pubblica su PyPI).
3. Nel progetto togli la cartella e aggiungi la dipendenza in `requirements.txt`. Gli import non cambiano.
