# TT-open — Deployment

## 1. Overview

Production-середовище TT-open розгортається через Railway.

Основна схема:

```text
GitHub
   ↓
Railway
   ↓
Docker build
   ↓
Application
   ↓
PostgreSQL