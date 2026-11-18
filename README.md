# 3DPrint — портал заказа 3D-печати (MVP)

Модульный монолит: Django 6 + DRF + django-rq + PostgreSQL 16 + Redis 7 + MinIO + React/TypeScript/Vite/Tailwind/three.js.
Весь интерфейс — на русском языке.

> ⚠️ Код написан без возможности запуска Django/npm в среде генерации: формулы цены проверены на эталонных кейсах, остальное (миграции, pytest, `npm run build`) нужно прогнать у себя — см. раздел 7.

## 1. Запуск в Docker
```bash
cp .env.example .env
docker compose up --build
```
При старте backend сам создаёт бакет, применяет миграции и загружает справочники (`seed_catalog`).

| Сервис | Адрес |
|---|---|
| SPA | http://localhost:5173 |
| API / Swagger | http://localhost:8000/api/docs |
| Django Admin | http://localhost:8000/admin/ |
| MinIO консоль | http://localhost:9001 |
| Mailpit | http://localhost:8025 |

## 2. Запуск без Docker
Backend (Python 3.12):
```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env
```
В `.env` замените хосты: `POSTGRES_HOST=localhost`, `REDIS_HOST=localhost`, `MINIO_ENDPOINT=http://localhost:9000`,
`EMAIL_HOST=localhost`, `VITE_PROXY_TARGET=http://localhost:8000`.

Минимальный вариант вообще без внешних сервисов — раскомментируйте в `.env`:
`USE_SQLITE=True`, `USE_LOCAL_STORAGE=True`, `TASKS_SYNC=True`.

```bash
python manage.py makemigrations     # один раз, см. примечание о миграциях
python manage.py migrate
python manage.py seed_catalog
python manage.py runserver
# в отдельном терминале (если не TASKS_SYNC): python manage.py rqworker default
```
Frontend:
```bash
cd frontend
npm install
npm run dev
```

## 3. Демо-пользователи (`seed_catalog`)
| Роль | Email | Пароль |
|---|---|---|
| Администратор | admin@3dprint.local | Admin123! |
| Менеджер | manager@3dprint.local | Manager123! |
| Клиент | client@3dprint.local | Client123! |

## 4. Тесты и проверки
```bash
cd backend && pytest
python manage.py makemigrations --check --dry-run
flake8 . --count --select=E9,F63,F7,F82
cd ../frontend && npm run build
```

## 5. Интеграционный API
Создайте `ApiClient` в `/admin/` либо из shell: `ApiClient.issue('engineer', ['orders:read','orders:write','export:read'])`
(ключ показывается один раз, в БД хранится хэш). Передавайте заголовок `X-API-Key`.

## 6. Отличия от исходного scaffold
- В `docker-compose.yml` фронтенд использует `VITE_API_URL=/api` и проксирует `/api`, `/admin` через Vite (одно происхождение — проще с cookie/CSRF).
- `users.User` расширен миграцией `0002_extend_user.py`; `0001_initial.py` не изменялся.

## 7. Первый запуск: что нужно сделать один раз
1. `cd backend && python manage.py makemigrations` — сгенерировать и закоммитить миграции новых приложений (`users/0002_extend_user.py` уже есть и зависит от вашего `0001_initial`).
2. `cd frontend && npm install` — создаст `package-lock.json` (нужен для `npm ci` в CI), затем закоммитьте его.
3. `pytest` в `backend/` и `npm run build` во `frontend/`; при ошибках типов/импортов поправьте точечно.
