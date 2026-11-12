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
├── views.py             # viste d'errore di Django in JSON (CSRF, 400, 403, 404, 500)
├── auth.py              # validazione password, login a sessione, validatori password
├── audit.py             # registro delle operazioni (modello astratto + log_write)
├── updates.py           # modifica parziale di un oggetto
├── fields.py            # campi a scelta, importi, vincoli CHECK
├── access.py            # lettura di un oggetto accessibile all'utente, o 404
├── db.py                # QuerySet con filtro di accesso, subquery, controllo di unicità
├── dates.py             # date mensili e scadenze
├── validators.py        # normalizzazione di dati personali generici
├── it.py                # dati italiani: codice fiscale
├── mail.py              # invio email con modalità demo
├── testing/
│   ├── runner.py        # VerboseTestRunner: output leggibile dei test
│   └── api.py           # helper per i test delle API
└── tests/               # test del framework
```

Dipendenze interne: `errors` → `messages`; `api` → `errors`, `messages`; `views` → `messages`;
`access` → `errors`; `auth` → `errors`, `messages`; `db` → `errors`, `messages`; `audit` → `fields`;
`updates` → `errors`, `messages`, `audit` (`snapshot`, `diff`). Tutti gli altri moduli sono indipendenti tra loro.

`djkit` non ha un modulo `models`: i modelli astratti (`audit.AuditEntryBase`) si importano dal loro modulo e
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
| `DJKIT_TEST_EXCLUDED_DIRS` | `{"tests", "migrations", ".venv", "venv", "site-packages"}` | `testing.runner` | parti di percorso mai mostrate come "codice sotto test"; il valore **sostituisce** il default. Le cartelle del modulo settings (da `SETTINGS_MODULE`, es. `config` per `config.settings`) sono sempre escluse in aggiunta | ✅ |
| `DJKIT_TEST_EXCLUDED_FILES` | `{"tests.py", "factories.py", "apps.py", "admin.py", "__init__.py"}` | `testing.runner` | nomi di file mai mostrati come "codice sotto test"; il valore **sostituisce** il default | ✅ |
| `DJKIT_AUDIT_EXCLUDED_FIELDS` | `{"password"}` | `audit`, `updates` | campi mai scritti nel registro (né nelle `snapshot`, né nei `diff`); il valore **sostituisce** il default | ✅ |
| `DJKIT_MESSAGES` | `{}` | `messages` (e quindi `errors`, `api`, `views`, `auth`, `db`, `updates`) | testi dei messaggi per l'utente, `{chiave: testo}`; le chiavi assenti restano col testo inglese di `DEFAULT_MESSAGES`. Un progetto in un'altra lingua le fornisce **tutte** (vedi §4.0) | ✅ |
| `DJKIT_DEMO_MODE` | `False` | `mail` | se vero le email non partono e vengono solo registrate nel log (il progetto può passarlo anche come parametro) | 📝 |

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
  - `db`/`updates`: `unique`, `field_not_editable`;
  - `auth`: `login_failed`, `password_too_short` (`{min_length}`), `password_too_similar`;
  - errori HTTP: `bad_request`, `unauthorized`, `forbidden`, `csrf_failed`, `method_not_allowed`,
    `too_many_requests`, `server_error`;
  - validazione degli schemi: `missing`, `invalid_value`, `invalid_json`, `string_type`, `string_too_short`
    (`{min_length}`), `string_too_long` (`{max_length}`), `number_type`, `boolean_type`, `date_type`,
    `datetime_type`, `greater_than` (`{gt}`), `greater_than_equal` (`{ge}`), `less_than` (`{lt}`),
    `less_than_equal` (`{le}`), `max_digits` (`{max_digits}`), `decimal_places` (`{decimal_places}`), `choice`,
    `list_type`, `object_type`.
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
| `NotFound` | 404 | `not_found` (`Not found.`) | oggetto inesistente **o non accessibile** all'utente: non si rivela che esiste |
| `Conflict` | 409 | `conflict` (`Conflict with the current state.`) | conflitto con lo stato attuale (valore già usato, oggetto in sola lettura, ...) |
| `InvalidData` | 422 | `invalid_data` (`Invalid data.`) | violazione di una regola non coperta dalla validazione dello schema |
| `ConfirmationRequired(impact, required, given, detail=None)` | 428 | `confirmation_required` (`Confirmation required.`) | operazione distruttiva non ancora confermata abbastanza volte |

- Ogni eccezione ha `detail` (messaggio per l'utente; se manca, `get_message(message_key)` della classe, quindi
  il testo di `DJKIT_MESSAGES` se il progetto lo fornisce) ed `extra`
  (dati aggiuntivi per il corpo della risposta; i valori `None` vengono scartati).
  `payload() -> dict` restituisce `{"detail": ..., **extra}`.
- `InvalidData(detail=None, errors={"campo": ["messaggio", ...]})`: errori legati ai campi.
- `InvalidData.from_validation_error(error) -> InvalidData`: converte una `ValidationError` di Django.
  Gli errori dei campi finiscono in `errors` (quelli generali sotto `"__all__"`), gli altri messaggi in `detail`.
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
    solleva `ValueError`) il messaggio del validatore stesso; tipi sconosciuti → `invalid_value`.
- `ErrorOut`: schema `{detail: str, errors?: {campo: [str]}, impact?: dict, required?: int, given?: int}`.
- `ConfirmationIn`: schema `{confirmations: int = 0}` (≥ 0), il numero di conferme date dal client.
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

```python
# settings.py
CSRF_FAILURE_VIEW = "djkit.views.csrf_failure"
# urls.py (URLconf principale)
handler404 = "djkit.views.page_not_found"   # e così handler400, handler403, handler500
```

Con `DEBUG` attivo Django continua a mostrare le sue pagine tecniche di 404 e 500.

### 4.2b `auth` — Password e login a sessione ✅

Funzionano con qualunque modello utente (usano solo `django.contrib.auth`).

- `validate_new_password(password: str, user=None, field: str = "password") -> None`: applica
  `AUTH_PASSWORD_VALIDATORS`; se la password non va bene solleva `InvalidData(errors={field: [messaggi]})`.
  `user` (anche non ancora salvato) permette ai validatori di confrontare la password con i dati dell'utente.
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

### 4.3 `audit` — Registro delle operazioni ✅

- `AuditAction`: valori ammessi di `action` (`CREATE`, `UPDATE`, `DELETE`).
- `AuditEntryBase` (modello **astratto**):

  | Campo | Tipo | Significato |
  |---|---|---|
  | `actor` | FK a `AUTH_USER_MODEL`, `SET_NULL`, `related_name="%(app_label)s_%(class)s_entries"` | chi ha fatto la modifica |
  | `action` | `choice_field(AuditAction)` | tipo di operazione |
  | `model` | `CharField(100)` | nome del modello modificato |
  | `object_id` | `PositiveBigIntegerField`, null | chiave dell'oggetto |
  | `object_label` | `CharField(300)` | `str(obj)` al momento della modifica |
  | `changes` | `JSONField` | `{"campo": [vecchio, nuovo]}` oppure la `snapshot` |
  | `timestamp` | `DateTimeField(auto_now_add)` | quando |

  Nel `Meta` sono definiti: ordinamento dal più recente, `verbose_name` "audit log entry" e il vincolo CHECK
  `"<app>_<classe>_action_valid"`. Se la sottoclasse ridefinisce `Meta.constraints`, deve rimettere il vincolo con
  `AuditEntryBase.action_constraint(name)`.

  Il `related_name` di `actor` è diverso per ogni sottoclasse: per `shop.OrderLog` vale
  `user.shop_orderlog_entries`. Così un progetto può avere più modelli concreti di registro senza conflitti
  (errori `fields.E304` / `E305`) e senza ridefinire `actor`.

```python
class AuditLogEntry(AuditEntryBase):
    team_id = models.PositiveBigIntegerField(null=True)

log_write(AuditLogEntry, request.user, AuditAction.UPDATE, invoice, changes, team_id=invoice.team_id)
```

- `log_write(entry_model, actor, action, obj, changes=None, **context) -> AuditEntryBase`: crea una voce del
  registro e va chiamata dentro la stessa transazione della scrittura. Per `DELETE` va chiamata **prima**
  di `obj.delete()`.
  - Se `changes` è `None`, salva la `snapshot` completa per `CREATE` e `DELETE` e `{}` per `UPDATE`.
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
  5. Restituisce il `diff` (senza i campi esclusi dal registro), pronto per `log_write`. Restituisce `{}` se
     non è cambiato nulla.

### 4.5 `access` — Oggetti accessibili ✅

- `get_accessible_or_404(source, user, pk, *, for_update=False, detail=None)`: restituisce
  `source.accessible_by(user).get(pk=pk)` oppure solleva `NotFound(detail)`.
  - `source` può essere un modello, un manager o un QuerySet; un QuerySet mantiene i suoi filtri.
  - Anche una chiave malformata (per esempio `"abc"` per un intero) dà `NotFound`, mai un errore 500.
  - Con `for_update` usa `select_for_update()`: va chiamata dentro `transaction.atomic()`.
  - Richiede un QuerySet con il metodo `accessible_by` (vedi `db.AccessibleQuerySet`).

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
  - `_model(name)`: restituisce un altro modello della **stessa app** del modello, senza import circolari.
- `sum_subquery(queryset, field: str = "amount", max_digits: int = 14, decimal_places: int = 2) -> Coalesce`:
  subquery correlata con la somma di un campo, come `DecimalField(max_digits, decimal_places)`. Se non ci sono
  righe restituisce 0 con `decimal_places` decimali (`Decimal("0.00")`). Si usa in `annotate()`.
- `count_subquery(queryset) -> Coalesce`: subquery correlata con il numero di righe, 0 se non ce ne sono.
- `date_filter(field: str, as_of: date | None) -> Q`: restituisce `Q(field__lte=as_of)`, oppure `Q()` vuoto
  se `as_of` è `None`.
- `ensure_unique(model, values: dict, exclude_pk=None, messages: dict | None = None) -> None`: controlla ogni campo
  di `values` (già normalizzato; i `None` sono saltati) e, se un'altra riga usa già quel valore, solleva
  `Conflict(errors={campo: [messaggio]})` con tutti i campi occupati; `detail` unisce i messaggi distinti.
  `exclude_pk` esclude la riga in modifica; `messages` (`{campo: testo}`) sostituisce, per i campi indicati, il
  messaggio generico della chiave `unique`. Si chiama prima di salvare, per rispondere 409 invece di 422.

```python
ensure_unique(Customer, {"email": email, "vat_number": vat}, exclude_pk=customer.pk)
```

### 4.7 `dates` — Date mensili ✅

Funzioni pure, senza database.

- `clamped_date(year, month, day) -> date`: costruisce la data, riportando `day` all'ultimo giorno del mese
  se il mese è più corto (31 aprile → 30 aprile).
- `add_months(year, month, months) -> tuple[int, int]`: sposta `(anno, mese)` in avanti di `months` mesi,
  gestendo il cambio d'anno.
- `monthly_due_dates(start_date, end_date) -> list[date]`: la prima scadenza è `start_date`, poi lo stesso giorno
  di ogni mese (adattato alla lunghezza del mese, senza "slittare": 31/1 → 28/2 → 31/3), fino a `end_date`
  incluso. Lista vuota se `end_date < start_date`.

### 4.8 `validators` e `it` — Dati personali ✅

- `validators.normalize_email_address(value: str | None) -> str | None`: toglie gli spazi e converte in minuscolo.
  `None` resta `None`.
- `it.TAX_CODE_LENGTH = 16`
- `it.validate_tax_code`: `RegexValidator` che accetta esattamente 16 lettere maiuscole o cifre
  (codice `invalid_tax_code`).
- `it.normalize_tax_code(value: str | None) -> str | None`: toglie gli spazi e converte in maiuscolo.

### 4.9 `mail` — Invio email 📝

- `send_email(subject, body, to: list[str], *, reply_to: list[str] | None = None, demo_mode: bool | None = None) -> bool`:
  invia con `django.core.mail.EmailMessage`. Con la modalità demo attiva (parametro, oppure `DJKIT_DEMO_MODE`)
  l'email non parte e viene solo registrata nel log. Restituisce `True` se l'email è stata inviata.

### 4.10 `testing.runner` — Output leggibile dei test ✅

- `VerboseTestRunner` (`DiscoverRunner`): stampa una riga per test, raggruppata per modulo e classe.
  Ogni riga riporta esito, nome leggibile, durata, file del progetto eseguiti (rilevati con `sys.monitoring`)
  e, sotto, la prima riga della docstring. Alla fine stampa un riepilogo.
  - `-v 0`: output standard di Django.
  - `-v 2`: aggiunge anche i messaggi di Django.
  - `--debug-sql` e `--pdb`: si usano le classi di Django.
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
  - `assertNotAccessible(client, method, path, data=None)`: verifica che la risposta sia 404 e mai 403,
    per i test di isolamento.

---

## 5. Da cartella a pacchetto installabile

Se `djkit` è incluso come cartella dentro un progetto, per renderlo un pacchetto:

1. Sposta la cartella `djkit/` in un repository a parte e aggiungi un `pyproject.toml` con nome `djkit`,
   versione uguale a `__version__` e dipendenze `Django` e `django-ninja`.
2. Crea il tag `vX.Y.Z` e installa con `pip install git+https://github.com/<utente>/djkit@vX.Y.Z`
   (oppure pubblica su PyPI).
3. Nel progetto togli la cartella e aggiungi la dipendenza in `requirements.txt`. Gli import non cambiano.
