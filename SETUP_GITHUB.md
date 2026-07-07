# GitHub Setup

Целевой репозиторий: `git@github.com:EvgeniyZh77/Project.git`

## Минимальные шаги

1. Скопировать содержимое этого каталога в корень репозитория `Project`.
2. Закоммитить и отправить изменения.
3. Открыть `Settings -> Secrets and variables -> Actions`.
4. Добавить:

`Secrets`

- `OPENAI_API_KEY`
- `ARVAD_BITRIX_WEBHOOK_URL`

`Variables`

- `ARVAD_BITRIX_DIALOG_ID=chat4071`
- `OPENAI_MODEL=gpt-5-mini`

5. Открыть `Actions -> ARVAD Weekly Market Brief`.
6. Нажать `Run workflow`.

## Что проверить после первого запуска

- Появился ли новый HTML в `Artifacts`.
- Ушёл ли HTML в Bitrix24 чат `ТОП-менеджмент`.
- Сохранились ли свежие файлы в `output/`.

## Важно

- В текущей среде Codex не смог напрямую достучаться до GitHub, поэтому пакет подготовлен локально в готовом для пуша виде.
- Локальные файлы из `macos/` нужны только как резервный вариант запуска с Mac.
