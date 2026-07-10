# DotaCounterPeak

Telegram-бот на Python со статистикой героев Dota 2 для ранга «Титан» (Immortal).

Бот больше не использует профессиональные матчи и не выдаёт их за полезные паблик-матчапы. Для каждого героя он показывает общий винрейт, пикрейт и место по винрейту в рейтинговом All Pick на Immortal за последние 7 дней.

Готовый seed-файл уже лежит в `data/seed_immortal.json`. При каждом запуске бот проверяет его и синхронизирует локальную SQLite-базу.

## Команды

- `/heroes` — выбрать героя кнопкой.
- `/hero <герой>` — показать статистику героя.
- `/counter <герой>` — алиас `/hero`, оставлен для совместимости со старой версией.

Пример:

```text
/hero Anti-Mage
```

## Запуск

1. Создай и активируй виртуальное окружение:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Установи зависимости:

```powershell
pip install -r requirements.txt
```

3. Укажи токен Telegram-бота:

```powershell
$env:BOT_TOKEN="твой_токен_бота"
```

Либо скопируй `.env.example` в `.env` и заполни `BOT_TOKEN`.

4. Запусти бота:

```powershell
python bot.py
```

## Обновление статистики Immortal

Скрипт обновления использует STRATZ GraphQL API и запрашивает только:

- ранг `IMMORTAL`;
- режим `ALL_PICK_RANKED`;
- последние 7 дней;
- общий винрейт и пикрейт героев.

Получить бесплатный токен можно на [странице STRATZ API](https://stratz.com/api).

```powershell
$env:STRATZ_API_TOKEN="твой_токен_STRATZ"
powershell -ExecutionPolicy Bypass -File .\scripts\update_seed.ps1
```

Другой период от 1 до 30 дней:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_seed.ps1 -Days 14
```

Скрипт сначала проверяет ответ. Если данных нет или вернулось меньше 120 героев, рабочий seed-файл не перезаписывается. После успешного обновления перезапусти бота.

Источники:

- [STRATZ GraphQL API](https://api.stratz.com/graphiql) — повторяемое обновление статистики Immortal.
- [DOTABUFF Immortal heroes](https://www.dotabuff.com/heroes?date=7d&mode=all-pick&rankTier=immortal&show=heroes&view=winning) — исходный снимок, уже включённый в проект.
