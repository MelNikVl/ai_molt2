# Krisha Telegram Bot (MVP+)

Бот мониторит объявления krisha.kz и отправляет персональные уведомления пользователям в Telegram.

## Возможности

- Онбординг через inline-кнопки и шаги настройки фильтров (`/start`, `/settings`)
- Мультипользовательский режим (персональные фильтры)
- Подписки по ролям:
  - role=1 → 1 день
  - role=2 → 7 дней
  - role=3 → 30 дней
- Админ-команда в Telegram: `/grant USER_ID ROLE`
- Ежедневная сводка в выбранный пользователем час (UTC+5)
- Веб-панель администратора на `:8080`

## Структура проекта

```text
.
├── README.md
├── requirements.txt
└── krisha_bot
    ├── .env
    ├── admin_web.py
    ├── config.py
    ├── db.py
    ├── main.py
    ├── notifier.py
    ├── parser.py
    └── templates
        ├── base.html
        ├── dashboard.html
        ├── logs.html
        ├── login.html
        ├── subscriptions.html
        └── users.html
```

## Подготовка

1. Python 3.11+
2. Установить зависимости:

```bash
pip install -r requirements.txt
```

3. Заполнить `krisha_bot/.env`:

```env
BOT_TOKEN=...
ADMIN_TELEGRAM_ID=...
ADMIN_PASSWORD=...
CHECK_INTERVAL_MINUTES=15
DB_PATH=krisha_bot/krisha.db
TEST=false
```

## Запуск

```bash
cd krisha_bot
python main.py
```

После запуска:
- Telegram бот работает через long polling
- Веб-панель доступна на `http://localhost:8080/admin/login`

## Онбординг пользователя

1. `/start`
2. Выбрать город
3. Выбрать тип сделки
4. Ввести диапазон цены `100000-500000`
5. Ввести диапазон метража `40-80`
6. Ввести час сводки `20` (UTC+5)

## Администрирование

### Telegram

- `/grant USER_ID ROLE`

### Web

- `/admin` — дашборд
- `/admin/users` — пользователи + продлить/блокировка
- `/admin/subscriptions` — выдача подписки
- `/admin/logs` — последние 100 событий

