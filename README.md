# Locomotive - CI Load Testing Library

Python-библиотека и CLI для интеграции нагрузочного тестирования в CI/CD пайплайны. Использует Locust под капотом, но позволяет описывать тесты декларативно в JSON/YAML конфиге — без написания Python кода.

## Основные возможности

- **Декларативное описание тестов** — опиши эндпоинты в JSON, библиотека сгенерирует Locust-скрипт
- **Сравнение с baseline** — автоматический анализ регрессий производительности
- **HTML-отчёты** — наглядные результаты для PR/MR
- **GitHub Actions ready** — переменные окружения, exit codes, артефакты

## Быстрый старт

### 1. Установка

```bash
pip install locomotive locust
```

### 2. Создание конфига

```bash
# Базовый шаблон
loco init

# Или с предзаполнением из OpenAPI (шаблон для ручной правки)
loco init --openapi openapi.json

# С генерацией GitHub Actions workflow
loco init --github-workflow
```

### 3. Редактирование конфига

Открой `loconfig.json` и настрой эндпоинты:

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
    "mode": "acceptance",
    "gate": {
      "min_requests": 100,
      "thresholds": {
        "error_rate": {"fail": 0}
      }
    },
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
loco ci --config loconfig.json

# Установить baseline (обычно на main ветке)
loco ci --config loconfig.json --set-baseline
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

Правила ниже сравнивают метрики текущего прогона с baseline.

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

## Режимы проверки (gate)

Gate-проверки работают без baseline и применяются к метрикам текущего прогона.

### Resilience / capacity

```json
{
  "analysis": {
    "mode": "resilience",
    "gate": {
      "min_requests": 200,
      "thresholds": {
        "error_rate_non_503": {"fail": 2},
        "error_rate_503": {"fail": 5},
        "p95_ms": {"fail": 500},
        "p99_ms": {"fail": 800}
      }
    }
  }
}
```

### Acceptance / NFR compliance

```json
{
  "analysis": {
    "mode": "acceptance",
    "gate": {
      "min_requests": 100,
      "warmup_seconds": 10,
      "thresholds": {
        "error_rate": {"fail": 0},
        "failures": {"fail": 3}
      }
    }
  }
}
```

| Параметр | Описание |
|----------|----------|
| `mode` | `acceptance` (строго) или `resilience` (порог ошибок) |
| `gate.thresholds` | Пороговые проверки для метрик текущего прогона |
| `gate.min_requests` | Минимум запросов для применения gate |
| `gate.warmup_seconds` | Секунды warmup, игнорируются в расчёте ошибок |

В режиме `resilience` для error-метрик `warn` по умолчанию равен 0, поэтому любые ошибки ниже `fail` дают WARNING.

Дополнительно считаются метрики `error_rate_503`, `error_rate_4xx`, `error_rate_5xx`, `failures_503`, `failures_4xx`, `failures_5xx` и `error_rate_non_503` (всё кроме 503).

Если `mode` задан и метрики сохранены, код возврата определяется gate/analysis, а не выходным кодом Locust.

## GitHub Actions

### Использование готового Action (рекомендуется)

Самый простой способ — использовать готовый GitHub Action из библиотеки.

#### Публичный репозиторий (проще всего)

Если репозиторий `locomotive` публичный, токены не нужны:

**Важно:** 
- Замените `YOUR_ORG/locomotive` на реальное имя вашего репозитория (например, `loclocko/locomotive`)
- Укажите правильную ветку в `ref` (например, `master` или `main`)

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

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.9'

      - name: Checkout locomotive
        uses: actions/checkout@v4
        with:
          repository: YOUR_ORG/locomotive
          path: locomotive
          ref: master  # или main, в зависимости от вашей default branch

      - name: Run load test
        uses: ./locomotive/.github/actions/loadtest
        with:
          config: loconfig.json
          lib_repo: YOUR_ORG/locomotive

      - name: Set baseline
        if: github.ref == 'refs/heads/main'
        uses: ./locomotive/.github/actions/loadtest
        with:
          config: loconfig.json
          lib_repo: YOUR_ORG/locomotive
          set_baseline: true
```

#### Приватный репозиторий

Если репозиторий приватный, нужен Personal Access Token (PAT):

1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token (classic)
3. Выберите права: `repo` (полный доступ к репозиториям)
4. Скопируйте токен
5. В целевом репозитории: Settings → Secrets and variables → Actions → New repository secret
6. Name: `LOCOMOTIVE_TOKEN`
7. Value: вставьте токен

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

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.9'

      - name: Checkout locomotive
        uses: actions/checkout@v4
        with:
          repository: YOUR_ORG/locomotive
          path: locomotive
          token: ${{ secrets.LOCOMOTIVE_TOKEN }}
          ref: master  # или main, в зависимости от вашей default branch

      - name: Run load test
        uses: ./locomotive/.github/actions/loadtest
        with:
          config: loconfig.json
          lib_repo: YOUR_ORG/locomotive
          lib_token: ${{ secrets.LOCOMOTIVE_TOKEN }}

      - name: Set baseline
        if: github.ref == 'refs/heads/main'
        uses: ./locomotive/.github/actions/loadtest
        with:
          config: loconfig.json
          lib_repo: YOUR_ORG/locomotive
          lib_token: ${{ secrets.LOCOMOTIVE_TOKEN }}
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
          pip install "git+https://x-access-token:${{ secrets.LOCOMOTIVE_TOKEN }}@github.com/YOUR_ORG/locomotive.git"
      
      - name: Start service
        run: docker-compose up -d
      
      - name: Run load test
        run: loco ci --config loconfig.json
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
        run: loco ci --set-baseline
```

## CLI команды

```bash
# Инициализация конфига
loco init [--openapi spec.json] [--github-workflow]

# Полный пайплайн
loco ci --config loconfig.json

# Только запуск тестов
loco run --config loconfig.json

# Только анализ
loco analyze --config loconfig.json --baseline <run_id>

# Только отчёт
loco report --config loconfig.json
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
