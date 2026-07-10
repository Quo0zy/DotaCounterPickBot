import html
import logging
import os
import re
from pathlib import Path

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from storage import HeroStats, HeroStatsRepository, normalize_name

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")

db_path_value = os.getenv("DB_PATH")
DB_PATH = Path(db_path_value) if db_path_value else BASE_DIR / "dota_counter_peak.db"
SEED_PATH = BASE_DIR / "data" / "seed_immortal.json"
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
HEROES_PER_PAGE = 15

HELP_TEXT = """Команды:
/heroes — выбрать героя кнопкой
/hero <герой> — показать статистику героя
/counter <герой> — то же самое (оставлено для совместимости)

Пример: /hero Anti-Mage

Бот показывает общий винрейт и пикрейт в рейтинговом All Pick на ранге «Титан» (Immortal), а не статистику профессиональных матчей."""


repository = HeroStatsRepository(DB_PATH)


def command_argument(update: Update) -> str:
    text = update.effective_message.text if update.effective_message else ""
    return re.sub(r"^/\w+(?:@\w+)?\s*", "", text, count=1).strip()


def format_stats(stats: HeroStats) -> str:
    hero_name = html.escape(stats.name)
    return (
        f"<b>{hero_name}</b> — ранг «Титан»\n\n"
        f"<b>Винрейт:</b> {stats.win_rate:.2f}%\n"
        f"<b>Пикрейт:</b> {stats.pick_rate:.2f}%\n"
        f"<b>Место по винрейту:</b> {stats.meta_rank} из {stats.total_heroes}\n\n"
        "Период: последние 7 дней, рейтинговый All Pick."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, reply_markup=heroes_keyboard(0))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, reply_markup=heroes_keyboard(0))


async def hero_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    hero_name = command_argument(update)
    if not hero_name:
        await update.message.reply_text(
            "Напиши героя после команды, например: /hero Anti-Mage"
        )
        return

    stats = repository.get_hero(hero_name)
    if stats is None:
        await update.message.reply_text(
            "Не нашёл героя в базе. Можно выбрать его кнопкой:",
            reply_markup=heroes_keyboard(0),
        )
        return

    await update.message.reply_text(format_stats(stats), parse_mode=ParseMode.HTML)


async def heroes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    hero_names = repository.list_heroes()
    if not hero_names:
        await update.message.reply_text(
            "База пока пустая. Проверь, что рядом есть data/seed_immortal.json."
        )
        return

    await update.message.reply_text("Выбери героя:", reply_markup=heroes_keyboard(0))


async def plain_text_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text.strip()
    stats = repository.get_hero(text)
    if stats is None:
        await update.message.reply_text(
            "Не нашёл героя в базе. Можно выбрать его кнопкой:",
            reply_markup=heroes_keyboard(0),
        )
        return

    await update.message.reply_text(format_stats(stats), parse_mode=ParseMode.HTML)


async def hero_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if data == "noop":
        return

    if data.startswith("page:"):
        page = int(data.removeprefix("page:"))
        await query.edit_message_text(
            "Выбери героя:", reply_markup=heroes_keyboard(page)
        )
        return

    if data.startswith("hero:"):
        normalized_name = data.removeprefix("hero:")
        stats = repository.get_hero(normalized_name)
        if stats is None:
            await query.edit_message_text(
                "Не нашёл героя в базе.", reply_markup=heroes_keyboard(0)
            )
            return

        await query.edit_message_text(
            format_stats(stats),
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
                InlineKeyboardButton(
                    hero_name,
                    callback_data=f"hero:{normalize_name(hero_name)}",
                )
                for hero_name in page_heroes[index : index + 3]
            ]
        )

    navigation = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton("Назад", callback_data=f"page:{page - 1}")
        )
    navigation.append(
        InlineKeyboardButton(f"{page + 1}/{page_count}", callback_data="noop")
    )
    if page < page_count - 1:
        navigation.append(
            InlineKeyboardButton("Вперёд", callback_data=f"page:{page + 1}")
        )
    rows.append(navigation)

    return InlineKeyboardMarkup(rows)


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("hero", "статистика героя на ранге Титан"),
            BotCommand("counter", "то же самое, что /hero"),
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
    application.add_handler(CommandHandler(["counter", "hero"], hero_command))
    application.add_handler(CommandHandler("heroes", heroes))
    application.add_handler(CallbackQueryHandler(hero_button))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text_lookup)
    )
    return application


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    repository.initialize()
    if SEED_PATH.exists():
        seeded_count = repository.seed_from_file(SEED_PATH)
        logging.info("Seeded %s Immortal hero stats from %s", seeded_count, SEED_PATH)
    else:
        logging.warning("Seed file does not exist: %s", SEED_PATH)
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
