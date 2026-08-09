# TT-open — Business Rules

## 1. Purpose

TT-open контролює роботу торгових точок мережі та фіксує ключові події робочого дня:

- відкриття ТТ;
- запізнення;
- закриття ТТ;
- касу;
- фото/файл вечірнього чека;
- порушення дедлайнів;
- відповідальних користувачів;
- звіти по ТТ, кущах та всій мережі.

---

# 2. Main Entities

Основні бізнес-сутності:

- User
- Store
- Bush
- Cluster
- Schedule
- Schedule Exception
- Opening Check-in
- Closing Report
- Invite
- Notification
- Audit Log

---

# 3. User Roles

У системі використовуються ролі:

```text
ROOT_ADMIN
DIRECTOR
BUSH_ADMIN
LION
STORE_USER