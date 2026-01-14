# CI Loadtest Library

Python-библиотека и CLI для интеграции нагрузочного тестирования в CI/CD пайплайны. Использует Locust под капотом, но позволяет описывать тесты декларативно в JSON/YAML конфиге — без написания Python кода.

## Основные возможности

- **Декларативное описание тестов** — опиши эндпоинты в JSON, библиотека сгенерирует Locust-скрипт
- **Сравнение с baseline** — автоматический анализ регрессий производительности
- **HTML-отчёты** — наглядные результаты для PR/MR
- **GitHub Actions ready** — переменные окружения, exit codes, артефакты

## Быстрый старт

### 1. Установка

```bash
pip install ci-loadtest-lib locust
```

### 2. Создание конфига

```bash
# Базовый шаблон
ci-loadtest init

# Или с предзаполнением из OpenAPI (шаблон для ручной правки)
ci-loadtest init --openapi openapi.json

# С генерацией GitHub Actions workflow
ci-loadtest init --github-workflow
```

### 3. Редактирование конфига

Открой `ci-loadtest.json` и настрой эндпоинты:

```json
{
  "load": {
    "host": "http://localhost:8000",
    "users": 20,
    "spawn_rate": 5,
    "run_time": "1m"
  },
  "scenario": {
    "think_time": {"min": 0.5, "max": 2.0},
    "headers": {
      "Accept": "application/json"
    },
    "requests": [
      {
        "name": "Get Users",
        "method": "GET",
        "path": "/api/users",
        "weight": 5,
        "tags": ["api"]
      },
      {
        "name": "Create Order",
        "method": "POST",
        "path": "/api/orders",
        "weight": 2,
        "json": {"product_id": 1, "quantity": "${random}"},
        "tags": ["api", "mutation"]
      }
    ]
  },
  "analysis": {
    "rules": [
      {"metric": "p95_ms", "mode": "relative", "direction": "increase", "warn": 10, "fail": 25},
      {"metric": "error_rate", "mode": "absolute", "direction": "increase", "warn": 1, "fail": 5}
    ],
    "fail_on": "DEGRADATION"
  }
}
```

### 4. Запуск

```bash
# Полный CI пайплайн: тест → анализ → отчёт
ci-loadtest ci --config ci-loadtest.json

# Установить baseline (обычно на main ветке)
ci-loadtest ci --config ci-loadtest.json --set-baseline
```

## Формат конфига

### Секция `load`

```json
{
  "load": {
    "host": "http://localhost:8000",
    "users": 50,
    "spawn_rate": 10,
    "run_time": "2m",
    "stop_timeout": 10,
    "tags": ["api"],
    "exclude_tags": ["slow"]
  }
}
```

### Секция `scenario`

```json
{
  "scenario": {
    "think_time": {"min": 0.5, "max": 2.0},
    "headers": {
      "Accept": "application/json",
      "Content-Type": "application/json"
    },
    "auth": {
      "type": "bearer",
      "token": "${API_TOKEN}"
    },
    "on_start": [
      {
        "name": "Login",
        "method": "POST",
        "path": "/auth/login",
        "json": {"username": "${USER}", "password": "${PASS}"},
        "capture": {"auth_token": "data.token"}
      }
    ],
    "requests": [...]
  }
}
```

### Формат request

```json
{
  "name": "Create Resource",
  "method": "POST",
  "path": "/api/resources",
  "weight": 3,
  "headers": {"X-Custom": "value"},
  "query": {"filter": "active"},
  "json": {"field": "value", "ts": "${timestamp}"},
  "timeout": 30,
  "tags": ["api", "write"]
}
```

### Динамические значения

В строках поддерживаются плейсхолдеры:

| Плейсхолдер | Описание |
|-------------|----------|
| `${ENV_VAR}` | Переменная окружения |
| `${timestamp}` | Текущий timestamp (мс) |
| `${random}` | Случайная строка |
| `${iteration}` | Инкрементный счётчик |

### Авторизация

```json
// Bearer token
"auth": {"type": "bearer", "token": "${API_TOKEN}"}

// API Key
"auth": {"type": "api_key", "header": "X-API-Key", "key": "${API_KEY}"}

// Basic Auth
"auth": {"type": "basic", "username": "${USER}", "password": "${PASS}"}
```

## Правила анализа

```json
{
  "analysis": {
    "rules": [
      {
        "metric": "p95_ms",
        "mode": "relative",
        "direction": "increase",
        "warn": 10,
        "fail": 25
      }
    ],
    "fail_on": "DEGRADATION"
  }
}
```

| Параметр | Описание |
|----------|----------|
| `metric` | `p95_ms`, `p99_ms`, `avg_ms`, `rps`, `error_rate` |
| `mode` | `relative` (% от baseline) или `absolute` (абсолютное значение) |
| `direction` | `increase` (больше = хуже) или `decrease` (меньше = хуже) |
| `warn` / `fail` | Пороги для WARNING и DEGRADATION |
| `fail_on` | При каком статусе возвращать exit code 1 |

## GitHub Actions

### Использование готового Action (рекомендуется)

Самый простой способ — использовать готовый GitHub Action из библиотеки:

```yaml
name: Load Test

on:
  push:
    branches: [main]
  pull_request:

jobs:
  loadtest:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout project
        uses: actions/checkout@v4

      - name: Checkout ci-loadtest-lib
        uses: actions/checkout@v4
        with:
          repository: YOUR_ORG/ci-loadtest-lib
          path: ci-loadtest-lib
          token: ${{ secrets.CI_LOADTEST_LIB_TOKEN || github.token }}

      - name: Run load test
        uses: ./ci-loadtest-lib/.github/actions/loadtest
        with:
          config: ci-loadtest.json
          lib_repo: YOUR_ORG/ci-loadtest-lib

      - name: Set baseline
        if: github.ref == 'refs/heads/main'
        uses: ./ci-loadtest-lib/.github/actions/loadtest
        with:
          config: ci-loadtest.json
          lib_repo: YOUR_ORG/ci-loadtest-lib
          set_baseline: true
```

Action автоматически:
- ✅ Устанавливает зависимости
- ✅ Устанавливает библиотеку из приватного репо
- ✅ Скачивает baseline
- ✅ Запускает тесты
- ✅ Загружает результаты

### Ручная установка (альтернатива)

Если нужен больший контроль:

```yaml
name: Load Test

on:
  push:
    branches: [main]
  pull_request:

jobs:
  loadtest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install
        run: |
          pip install locust PyYAML
          pip install "git+https://x-access-token:${{ secrets.CI_LOADTEST_LIB_TOKEN }}@github.com/YOUR_ORG/ci-loadtest-lib.git"
      
      - name: Start service
        run: docker-compose up -d
      
      - name: Run load test
        run: ci-loadtest ci --config ci-loadtest.json
        env:
          API_TOKEN: ${{ secrets.API_TOKEN }}
      
      - name: Upload results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: loadtest-results
          path: artifacts/
      
      - name: Set baseline
        if: github.ref == 'refs/heads/main'
        run: ci-loadtest ci --set-baseline
```

## CLI команды

```bash
# Инициализация конфига
ci-loadtest init [--openapi spec.json] [--github-workflow]

# Полный пайплайн
ci-loadtest ci --config ci-loadtest.json

# Только запуск тестов
ci-loadtest run --config ci-loadtest.json

# Только анализ
ci-loadtest analyze --config ci-loadtest.json --baseline <run_id>

# Только отчёт
ci-loadtest report --config ci-loadtest.json
```

## Использование с готовым locustfile

Если есть существующий locustfile, можно использовать его вместо `scenario`:

```json
{
  "locust": {
    "locustfile": "tests/locustfile.py",
    "host": "http://localhost:8000",
    "users": 50,
    "spawn_rate": 10,
    "run_time": "2m"
  }
}
```

## Артефакты

```
artifacts/
├── baseline.json           # Текущий baseline
└── runs/
    └── <run_id>/
        ├── run.json        # Метаданные запуска
        ├── metrics.json    # Агрегированные метрики
        ├── analysis.json   # Результат анализа
        ├── report.html     # HTML отчёт
        ├── generated/      # Сгенерированный locustfile (если используется scenario)
        └── raw/            # Сырые CSV от Locust
```

## Требования

- Python 3.9+
- Locust (устанавливается отдельно)

## Лицензия

MIT
