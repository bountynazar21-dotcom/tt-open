# Дерево проєкту Chikin Bot

```text
chikin-bot/
├── app/
│   ├── api/                    # Health-check і webhook endpoints
│   ├── database/
│   │   ├── models/             # SQLAlchemy-моделі таблиць
│   │   └── repositories/       # Запити й операції з PostgreSQL
│   ├── enums/                  # Ролі, статуси та типи подій
│   ├── filters/                # Фільтри aiogram
│   ├── handlers/               # Telegram-команди та callback-обробники
│   ├── keyboards/              # Inline/Reply клавіатури
│   ├── middlewares/            # БД, авторизація, права, логування
│   ├── scheduler/              # Автоматичні перевірки відкриття/закриття
│   ├── schemas/                # Pydantic-схеми
│   ├── services/               # Бізнес-логіка системи
│   ├── states/                 # FSM-сценарії
│   ├── texts/                  # Тексти повідомлень українською
│   ├── utils/                  # Час, гроші, Excel, токени, валідація
│   ├── bot.py                  # Створення Bot і Dispatcher
│   ├── config.py               # Налаштування з .env
│   └── main.py                 # Точка запуску
├── alembic/                    # Міграції PostgreSQL
├── docs/                       # Архітектура та бізнес-правила
├── scripts/                    # Імпорт ТТ і службові скрипти
├── storage/                    # Тимчасові імпорти та готові звіти
├── tests/                      # Unit та integration тести
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── railway.toml
├── alembic.ini
├── pyproject.toml
└── README.md
```

## Принцип розподілу відповідальності

- `handlers` лише приймають Telegram-події й викликають сервіси.
- `services` містять бізнес-логіку відкриття, закриття, каси та звітів.
- `repositories` працюють із базою даних.
- `scheduler` запускає часові перевірки та сповіщення.
- `filters` і `middlewares` контролюють ролі та доступ до кущів/ТТ.
- `texts` зберігає тексти окремо від логіки.
