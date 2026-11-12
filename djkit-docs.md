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

---

## 2. Struttura

```
djkit/
├── __init__.py          # __version__
├── apps.py              # DjkitConfig (AppConfig)
├── CHANGELOG.md
├── djkit-docs.md        # questo file
├── errors.py            # eccezioni di dominio e conferme
├── api.py               # handler HTTP delle eccezioni, schemi comuni
├── audit.py             # registro delle operazioni (modello astratto + log_write)
├── updates.py           # modifica parziale di un oggetto
├── fields.py            # campi a scelta, importi, vincoli CHECK
├── access.py            # lettura di un oggetto accessibile all'utente, o 404
├── db.py                # QuerySet con filtro di accesso, subquery di somma/conteggio
├── dates.py             # date mensili e scadenze
├── validators.py        # normalizzazione di dati personali generici
├── it.py                # dati italiani: codice fiscale
├── mail.py              # invio email con modalità demo
├── testing/
│   ├── runner.py        # VerboseTestRunner: output leggibile dei test
│   └── api.py           # helper per i test delle API
└── tests/               # test del framework
```

Dipendenze interne: `api` → `errors`; `access` → `errors`; `audit` → `fields`;
`updates` → `errors`, `audit` (`snapshot`, `diff`). Tutti gli altri moduli sono indipendenti tra loro.

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
| `DJKIT_DEMO_MODE` | `False` | `mail` | se vero le email non partono e vengono solo registrate nel log (il progetto può passarlo anche come parametro) | 📝 |

`BASE_DIR` (setting standard dei progetti Django) è usato da `testing.runner` per decidere quali file appartengono
al progetto.

---

## 4. Moduli e funzionalità

### 4.1 `errors` — Eccezioni di dominio e conferme ✅

I service sollevano queste eccezioni senza conoscere HTTP. Le traduce in risposte `api.register_error_handlers`.

| Nome | Status HTTP | Messaggio predefinito | Quando |
|---|---|---|---|
| `DomainError(detail=None, **extra)` | 400 | `Request failed.` | classe base |
| `NotFound` | 404 | `Not found.` | oggetto inesistente **o non accessibile** all'utente: non si rivela che esiste |
| `Conflict` | 409 | `Conflict with the current state.` | conflitto con lo stato attuale (valore già usato, oggetto in sola lettura, ...) |
| `InvalidData` | 422 | `Invalid data.` | violazione di una regola non coperta dalla validazione dello schema |
| `ConfirmationRequired(impact, required, given, detail=None)` | 428 | `Confirmation required.` | operazione distruttiva non ancora confermata abbastanza volte |

- Ogni eccezione ha `detail` (messaggio per l'utente; se manca, `default_detail` della classe) ed `extra`
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

- `register_error_handlers(api: NinjaAPI, status_codes: dict | None = None) -> None`: registra un handler per ogni
  eccezione di `errors` (`DEFAULT_STATUS_CODES`) e per la `ValidationError` di Django (422). Il corpo della
  risposta è `exc.payload()`. `status_codes` aggiunge o sostituisce degli status, per esempio
  `{PaymentRequired: 402}` per un'eccezione del progetto. Una sottoclasse non registrata usa lo status della classe
  registrata più vicina, perché Ninja cerca l'handler lungo l'MRO.
- `ErrorOut`: schema `{detail: str, errors?: {campo: [str]}, impact?: dict, required?: int, given?: int}`.
- `ConfirmationIn`: schema `{confirmations: int = 0}` (≥ 0), il numero di conferme date dal client.

```python
api = NinjaAPI(auth=django_auth)   # django_auth (cookie di sessione) controlla già il token CSRF
register_error_handlers(api)
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
     sollevano `InvalidData(errors={campo: [...]})`.
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
