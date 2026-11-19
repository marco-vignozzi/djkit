# djkit

Blocchi riusabili per progetti **Django + Django Ninja**: autenticazione,
audit, controllo accessi, helper per API, paginazione, date, numeri,
validazione e messaggi. Non importa mai il progetto che lo usa.

Documentazione completa: [`djkit-docs.md`](djkit-docs.md).
Modifiche per versione: [`CHANGELOG.md`](CHANGELOG.md).

## Installazione

```bash
pip install "djkit @ git+https://github.com/marco-vignozzi/djkit.git@v0.7.0"
```

Nel `requirements.txt` del progetto la stessa riga va pinnata al tag.
Aggiungi `djkit` a `INSTALLED_APPS`.

## Sviluppo

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
docker run -d -e POSTGRES_PASSWORD=djkit -e POSTGRES_DB=djkit_test -p 55432:5432 postgres:18
DJANGO_SETTINGS_MODULE=testproject.settings .venv/bin/python -m django test djkit
```

I test richiedono PostgreSQL. Host, porta, utente e password si cambiano con
le variabili `DJKIT_TEST_DB_*` (vedi `testproject/settings.py`).

## Versioni

Versionamento semantico. Ogni release è un tag `vX.Y.Z` e il tag deve coincidere
con `__version__` in `src/djkit/__init__.py`. Ogni modifica va annotata in
`CHANGELOG.md`.
