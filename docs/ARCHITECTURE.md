# TT-open — Architecture

## 1. Overview

TT-open — це Telegram-бот для контролю роботи мережі торгових точок.

Основні задачі системи:

- контроль відкриття ТТ;
- фіксація запізнень;
- контроль закриття ТТ;
- прийом вечірніх звітів;
- фіксація каси;
- прийом фото/файлу чека;
- формування денних, тижневих і місячних звітів;
- контроль доступів користувачів;
- робота з кущами, кластерами та ТТ;
- автоматичні нагадування;
- автоматичні повідомлення про порушення;
- Telegram-звіти по регіонах;
- загальний підсумок по мережі;
- Excel-експорт;
- аудит критичних адміністративних змін.

---

## 2. Technology Stack

Основний стек:

- Python 3.12
- aiogram 3
- SQLAlchemy 2
- PostgreSQL
- asyncpg
- Alembic
- FastAPI
- APScheduler
- openpyxl
- Pydantic Settings
- Railway

Система побудована асинхронно.

---

## 3. Main Application Layers

Архітектура проєкту поділена на окремі рівні.

```text
Telegram
   │
   ▼
Handlers
   │
   ▼
Services
   │
   ▼
Repositories
   │
   ▼
SQLAlchemy
   │
   ▼
PostgreSQL