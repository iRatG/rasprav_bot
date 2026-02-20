# Telegram-бот записи на массаж

## Быстрый старт

### 1. Настройка окружения

Отредактируй `.env` — он уже создан с реальным токеном бота.
Обязательно замени заглушки:

```
WEBHOOK_SECRET=  ← сгенерируй: python -c "import secrets; print(secrets.token_hex(32))"
WEBHOOK_URL=     ← ngrok URL для локальной разработки (см. ниже)
POSTGRES_PASSWORD=  ← любой надёжный пароль
DATABASE_URL=    ← обнови с новым паролем
SYNC_DATABASE_URL= ← обнови с новым паролем
ADMIN_SECRET_KEY= ← сгенерируй: python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Запуск PostgreSQL

```bash
docker compose up db -d
```

### 3. Применение миграций (создание таблиц)

```bash
docker compose run --rm app alembic upgrade head
```

### 4. Добавление мастера в БД

Подключись к PostgreSQL и вставь запись мастера (нужен реальный Telegram user_id):

```bash
docker compose exec db psql -U postgres -d massage_bot
```

```sql
INSERT INTO masters (display_name, tg_user_id, timezone, work_start_time, work_end_time, buffer_min)
VALUES ('Имя мастера', 123456789, 'Europe/Moscow', '09:00', '20:00', 10);

-- Добавь цены на услуги (id услуг: 1 = Массаж спины, 2 = Массаж ног)
INSERT INTO master_service_prices (master_id, service_id, price, active_from)
VALUES (1, 1, 1500.00, '2025-01-01'),
       (1, 2, 1200.00, '2025-01-01');
```

### 5. Настройка ngrok (для webhook локально)

```bash
ngrok http 8000
```

Скопируй HTTPS URL (например `https://abc123.ngrok.io`) и вставь в `.env`:
```
WEBHOOK_URL=https://abc123.ngrok.io/webhook
```

### 6. Запуск приложения

```bash
docker compose up app
```

Бот доступен в Telegram, веб-админка: `http://localhost:8000/admin`

---

## Команды разработки

```bash
# Поднять всё
docker compose up

# Остановить
docker compose down

# Пересобрать образ (после изменений requirements.txt)
docker compose build app

# Новая миграция (после изменения моделей)
docker compose run --rm app alembic revision --autogenerate -m "описание"

# Применить миграции
docker compose run --rm app alembic upgrade head

# Откатить последнюю миграцию
docker compose run --rm app alembic downgrade -1

# Посмотреть логи
docker compose logs -f app
```

---

## Структура проекта

```
tg_m/
├── .env                    ← секреты (не в git)
├── .env.example            ← шаблон
├── docker-compose.yml
└── app/
    ├── main.py             ← точка входа (FastAPI + webhook)
    ├── config.py           ← конфиг из .env
    ├── bot/                ← aiogram хэндлеры
    │   ├── handlers/
    │   │   ├── client.py   ← сценарии клиента
    │   │   └── master.py   ← сценарии мастера
    │   ├── keyboards/      ← inline-клавиатуры
    │   ├── middleware.py   ← DB session middleware
    │   └── router.py       ← регистрация роутеров
    ├── db/
    │   ├── session.py      ← async + sync движки
    │   └── models/         ← SQLAlchemy модели (8 таблиц)
    ├── services/
    │   ├── slots.py        ← генерация свободных слотов
    │   ├── appointments.py ← создание/отмена записей
    │   └── notifications.py← шаблоны сообщений
    ├── scheduler/
    │   └── tasks.py        ← APScheduler (напоминания, реактивация)
    ├── web/
    │   ├── auth.py         ← верификация Telegram Login Widget
    │   ├── app.py          ← Flask-Admin
    │   └── admin/views.py  ← 5 страниц админки
    └── migrations/         ← Alembic
        └── versions/
            └── 0001_initial.py
```
