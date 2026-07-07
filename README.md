# ARVAD Weekly Market Brief

Репозиторий для еженедельной HTML-сводки ARVAD GROUP.

## Что делает automation

- Каждый понедельник в `07:30` по Екатеринбургу запускает weekly-pass.
- Собирает сигналы по обязательным источникам, конкурентам и открытым каналам.
- Формирует `HTML`, `JSON` и `Markdown`.
- Отправляет полную HTML-версию в Bitrix24.
- Если запуск идёт локально на Mac и нет интернета, сводка не строится по старым данным, а попытка переносится на 1 час.

## Структура

- `.github/workflows/arvad-daily-brief.yml` - облачный weekly-runner для GitHub Actions.
- `scripts/build_arvad_market_brief.py` - основной сборщик.
- `requirements.txt` - зависимости Python.
- `macos/` - локальные сценарии запуска на Mac, если нужен резервный вариант помимо GitHub.

## Что настроить в GitHub

Добавить `Secrets`:

- `OPENAI_API_KEY`
- `ARVAD_BITRIX_WEBHOOK_URL`

Добавить `Variables`:

- `ARVAD_BITRIX_DIALOG_ID`
  Значение: `chat4071`
- `OPENAI_MODEL`
  Значение по умолчанию: `gpt-5-mini`

## Расписание

- Текущий cron: `30 2 * * 1`
- Это соответствует `07:30` каждый понедельник по `Asia/Yekaterinburg`

## Локальная проверка

```bash
python3 -m pip install -r requirements.txt
python3 scripts/build_arvad_market_brief.py --lookback-hours 168
```

Для отправки в Bitrix24:

```bash
export ARVAD_BITRIX_WEBHOOK_URL='https://team.arvad.ru/rest/.../'
export ARVAD_BITRIX_DIALOG_ID='chat4071'
python3 scripts/build_arvad_market_brief.py --lookback-hours 168 --send-bitrix
```

## Что осталось сделать

1. Залить содержимое этого каталога в репозиторий `git@github.com:EvgeniyZh77/Project.git`.
2. Включить `GitHub Actions`.
3. Добавить `Secrets` и `Variables`.
4. Запустить `workflow_dispatch` один раз вручную для проверки.
