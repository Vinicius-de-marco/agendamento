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
O painel do dono fica em http://127.0.0.1:8000/painel/ (entre com o usuário definido como dono do negócio no admin).
O banco em desenvolvimento é SQLite (`db.sqlite3`).

## Lembretes no WhatsApp

O comando abaixo envia o lembrete para agendamentos que começam nas próximas 24h
(cada agendamento recebe um só). Rode a cada 15 minutos pelo cron:

```bash
*/15 * * * * cd /caminho/do/projeto && .venv/bin/python manage.py enviar_lembretes
```

O lembrete traz um link (`/<slug>/agendamento/<token>/`) onde o cliente confirma ou cancela.
O dono recebe no WhatsApp do negócio um aviso a cada novo agendamento e a cada cancelamento feito pelo cliente.

Por enquanto nenhuma mensagem é enviada de verdade: o padrão (`WHATSAPP_BACKEND=agenda.whatsapp.ConsoleBackend`)
só escreve as mensagens no console. Para usar um provedor real, crie uma classe com o método
`enviar(numero, texto)` e aponte `WHATSAPP_BACKEND` para ela no `.env`. Defina também `SITE_URL`
com o endereço público do site, que é usado nos links.

## Verificação

```bash
python manage.py check
python manage.py test
```
