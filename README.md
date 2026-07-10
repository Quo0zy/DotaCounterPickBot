# DotaCounterPeak

Telegram-бот на Python для просмотра контрпиков и хороших матчапов героев Dota 2.

База уже заполнена из статистики OpenDota: при запуске бот читает `data/seed_matchups.json` и загружает всех героев в локальную SQLite-базу.

## Что умеет

- `/heroes` - показывает кнопки с героями.
- `/counter <герой>` или `/hero <герой>` - ищет героя по названию.

Порядок в списках важен: `1` - самый сильный матчап.

## Запуск

1. Создай виртуальное окружение:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Установи зависимости:

```powershell
pip install -r requirements.txt
```

3. Создай бота через BotFather и укажи токен. Можно через переменную окружения:

```powershell
$env:BOT_TOKEN="твой_токен_бота"
```

Или скопируй `.env.example` в `.env` и впиши токен туда.

4. Запусти:

```powershell
python bot.py
```

## Как пользоваться в Telegram

1. Напиши `/start` или `/heroes`.
2. Выбери героя кнопкой.
3. Бот покажет:
   - 3 героя, против которых выбранный герой играет лучше всего;
   - 3 героя, которые сильнее всего играют против выбранного героя.

Также можно искать текстом:

```text
/counter Anti-Mage
```

## Обновление готовой базы

Seed-файл уже лежит в проекте. Если нужно пересобрать его по свежей статистике OpenDota:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update_seed.ps1
```

После этого перезапусти бота. При старте он загрузит обновленные данные в SQLite.

Источник данных:

- `http://api.opendota.com/api/heroes`
- `http://api.opendota.com/api/heroes/{hero_id}/matchups`
