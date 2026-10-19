# Agendamento

Agendamento online para pequenos negócios com lembrete no WhatsApp.

## Como rodar (desenvolvimento)

Requer Python 3.12+ (testado com Python 3.14).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # depois troque o SECRET_KEY
python manage.py migrate
python manage.py runserver
```

O admin fica em http://127.0.0.1:8000/admin/ (crie um usuário com `python manage.py createsuperuser`).
A página pública de cada negócio fica em http://127.0.0.1:8000/<slug-do-negocio>/ (a raiz `/` ainda não tem página).
O banco em desenvolvimento é SQLite (`db.sqlite3`).

## Verificação

```bash
python manage.py check
python manage.py test
```
