import html
import logging
import os
import re
from pathlib import Path
from typing import Iterable

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from storage import HeroMatchups, MatchupRepository, normalize_name

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")

db_path_value = os.getenv("DB_PATH")
DB_PATH = Path(db_path_value) if db_path_value else BASE_DIR / "dota_counter_peak.db"
SEED_PATH = BASE_DIR / "data" / "seed_matchups.json"
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
HEROES_PER_PAGE = 15

HELP_TEXT = """Команды:
/heroes - выбрать героя кнопкой
/counter <герой> - найти героя по названию
/hero <герой> - то же самое

Пример: /counter Anti-Mage

В списках порядок важен: 1 - самый сильный матчап."""


def escape_lines(values: Iterable[str]) -> str:
    return "\n".join(f"{index}. {html.escape(value)}" for index, value in enumerate(values, 1))


repository = MatchupRepository(DB_PATH)


def command_argument(update: Update) -> str:
    text = update.effective_message.text if update.effective_message else ""
    return re.sub(r"^/\w+(?:@\w+)?\s*", "", text, count=1).strip()


def format_matchups(matchups: HeroMatchups) -> str:
    good = escape_lines(matchups.good_against)
    bad = escape_lines(matchups.bad_against)
    hero_name = html.escape(matchups.name)

    return (
        f"<b>{hero_name}</b>\n\n"
        f"<b>Хорошо играет против:</b>\n{good}\n\n"
        f"<b>Плохо играет против:</b>\n{bad}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, reply_markup=heroes_keyboard(0))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, reply_markup=heroes_keyboard(0))


async def counter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    hero_name = command_argument(update)
    if not hero_name:
        await update.message.reply_text("Напиши героя после команды, например: /counter Anti-Mage")
        return

    matchups = repository.get_hero(hero_name)
    if matchups is None:
        await update.message.reply_text(
            "Не нашел героя в базе. Можно выбрать его кнопкой:",
            reply_markup=heroes_keyboard(0),
        )
        return

    await update.message.reply_text(format_matchups(matchups), parse_mode=ParseMode.HTML)


async def heroes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    hero_names = repository.list_heroes()
    if not hero_names:
        await update.message.reply_text("База пока пустая. Проверь, что рядом есть data/seed_matchups.json.")
        return

    await update.message.reply_text("Выбери героя:", reply_markup=heroes_keyboard(0))


async def plain_text_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text.strip()
    matchups = repository.get_hero(text)
    if matchups is None:
        await update.message.reply_text("Не нашел героя в базе. Можно выбрать его кнопкой:", reply_markup=heroes_keyboard(0))
        return

    await update.message.reply_text(format_matchups(matchups), parse_mode=ParseMode.HTML)


async def hero_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if data == "noop":
        return

    if data.startswith("page:"):
        page = int(data.removeprefix("page:"))
        await query.edit_message_text("Выбери героя:", reply_markup=heroes_keyboard(page))
        return

    if data.startswith("hero:"):
        normalized_name = data.removeprefix("hero:")
        matchups = repository.get_hero(normalized_name)
        if matchups is None:
            await query.edit_message_text("Не нашел героя в базе.", reply_markup=heroes_keyboard(0))
            return

        await query.edit_message_text(
            format_matchups(matchups),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("К списку героев", callback_data="page:0")]]
            ),
        )


def heroes_keyboard(page: int) -> InlineKeyboardMarkup:
    hero_names = repository.list_heroes()
    page_count = max(1, (len(hero_names) + HEROES_PER_PAGE - 1) // HEROES_PER_PAGE)
    page = max(0, min(page, page_count - 1))
    start = page * HEROES_PER_PAGE
    page_heroes = hero_names[start : start + HEROES_PER_PAGE]

    rows = []
    for index in range(0, len(page_heroes), 3):
        rows.append(
            [
                InlineKeyboardButton(hero_name, callback_data=f"hero:{normalize_callback_name(hero_name)}")
                for hero_name in page_heroes[index : index + 3]
            ]
        )

    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton("Назад", callback_data=f"page:{page - 1}"))
    navigation.append(InlineKeyboardButton(f"{page + 1}/{page_count}", callback_data="noop"))
    if page < page_count - 1:
        navigation.append(InlineKeyboardButton("Вперед", callback_data=f"page:{page + 1}"))
    rows.append(navigation)

    return InlineKeyboardMarkup(rows)


def normalize_callback_name(hero_name: str) -> str:
    return normalize_name(hero_name)


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("counter", "показать матчапы героя"),
            BotCommand("hero", "то же самое, что /counter"),
            BotCommand("heroes", "выбрать героя кнопкой"),
            BotCommand("help", "помощь"),
        ]
    )


def build_application() -> Application:
    if not TOKEN:
        raise RuntimeError("Укажи токен бота в переменной окружения BOT_TOKEN.")

    application = Application.builder().token(TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler(["counter", "hero"], counter))
    application.add_handler(CommandHandler("heroes", heroes))
    application.add_handler(CallbackQueryHandler(hero_button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text_lookup))
    return application


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    repository.initialize()
    if SEED_PATH.exists():
        seeded_count = repository.seed_from_file(SEED_PATH)
        logging.info("Seeded %s heroes from %s", seeded_count, SEED_PATH)
    else:
        logging.warning("Seed file does not exist: %s", SEED_PATH)
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
