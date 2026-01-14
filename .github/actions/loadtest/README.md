# CI Load Test Action

GitHub Action для запуска нагрузочного тестирования с использованием ci-loadtest-lib.

## Использование

### Базовый пример

```yaml
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
```

### Полный пример с параметрами

```yaml
- name: Run load test
  uses: ./ci-loadtest-lib/.github/actions/loadtest
  with:
    config: ci-loadtest.json
    lib_repo: YOUR_ORG/ci-loadtest-lib
    lib_token: ${{ secrets.CI_LOADTEST_LIB_TOKEN }}
    users: 50
    run_time: 2m
    set_baseline: false
    baseline_artifact: loadtest-baseline
    results_artifact: loadtest-results
```

## Inputs

| Параметр | Описание | Обязательный | По умолчанию |
|----------|----------|--------------|--------------|
| `config` | Путь к конфигу ci-loadtest.json | Нет | `ci-loadtest.json` |
| `lib_repo` | Репозиторий библиотеки (owner/repo) | Да | - |
| `lib_token` | GitHub токен для доступа к приватному репо | Нет | `github.token` |
| `users` | Количество пользователей (переопределяет конфиг) | Нет | - |
| `run_time` | Время выполнения теста (переопределяет конфиг) | Нет | - |
| `set_baseline` | Установить этот запуск как baseline | Нет | `false` |
| `baseline_artifact` | Имя артефакта для baseline | Нет | `loadtest-baseline` |
| `results_artifact` | Имя артефакта для результатов | Нет | `loadtest-results` |

## Outputs

| Параметр | Описание |
|----------|----------|
| `metrics_path` | Путь к файлу metrics.json |
| `report_path` | Путь к файлу report.html |
| `status` | Статус теста (PASS/WARNING/DEGRADATION) |

## Пример использования outputs

```yaml
- name: Run load test
  id: loadtest
  uses: ./ci-loadtest-lib/.github/actions/loadtest
  with:
    config: ci-loadtest.json
    lib_repo: YOUR_ORG/ci-loadtest-lib

- name: Check status
  run: |
    echo "Status: ${{ steps.loadtest.outputs.status }}"
    echo "Metrics: ${{ steps.loadtest.outputs.metrics_path }}"
    echo "Report: ${{ steps.loadtest.outputs.report_path }}"
```

## Что делает action

1. Устанавливает зависимости (locust, PyYAML)
2. Устанавливает ci-loadtest-lib из указанного репозитория
3. Скачивает baseline артефакты (если есть)
4. Запускает нагрузочный тест
5. Загружает результаты в артефакты

## Требования

- Python 3.9+
- Конфиг `ci-loadtest.json` в репозитории
- Доступ к репозиторию библиотеки (если приватный)
