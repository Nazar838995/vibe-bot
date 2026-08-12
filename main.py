import asyncio
import logging
import random
import sqlite3
from datetime import date

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

TOKEN = ""

DB_NAME = "vibe.db"


from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()


# ============================================================
# ГЛАВНОЕ МЕНЮ
# ============================================================

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="👤 Моя анкета"),
            KeyboardButton(text="🔥 Найти человека"),
        ],
        [
            KeyboardButton(text="❤️ Мои лайки"),
            KeyboardButton(text="💬 Мои знакомства"),
        ],
        [
            KeyboardButton(text="🎲 Человек дня"),
            KeyboardButton(text="⚙️ Настройки"),
        ],
    ],
    resize_keyboard=True,
)


# ============================================================
# КЛАВИАТУРЫ АНКЕТЫ
# ============================================================

gender_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Парень"),
            KeyboardButton(text="Девушка"),
        ],
        [
            KeyboardButton(text="Другое"),
        ],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)


looking_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Парни"),
            KeyboardButton(text="Девушки"),
        ],
        [
            KeyboardButton(text="Все"),
        ],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)


confirm_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="✅ Да, создать"),
            KeyboardButton(text="🔄 Заполнить заново"),
        ],
    ],
    resize_keyboard=True,
)


# ============================================================
# FSM — СОСТОЯНИЯ СОЗДАНИЯ АНКЕТЫ
# ============================================================

class ProfileForm(StatesGroup):
    age_gate = State()
    name = State()
    age = State()
    city = State()
    gender = State()
    looking_for = State()
    interests = State()
    bio = State()
    photo = State()
    confirm = State()


# ============================================================
# DATABASE
# ============================================================

def get_db():
    connection = sqlite3.connect(DB_NAME)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_db()

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            city TEXT NOT NULL,
            gender TEXT NOT NULL,
            looking_for TEXT NOT NULL,
            interests TEXT NOT NULL,
            bio TEXT NOT NULL,
            photo_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS likes (
            liker_id INTEGER NOT NULL,
            liked_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,

            PRIMARY KEY (liker_id, liked_id)
        );

        CREATE TABLE IF NOT EXISTS skips (
            user_id INTEGER NOT NULL,
            skipped_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,

            PRIMARY KEY (user_id, skipped_id)
        );

        CREATE TABLE IF NOT EXISTS matches (
            user1_id INTEGER NOT NULL,
            user2_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,

            PRIMARY KEY (user1_id, user2_id)
        );
        """
    )

    connection.commit()
    connection.close()


# ============================================================
# DATABASE — ПРОФИЛЬ
# ============================================================

def get_profile(user_id: int):
    connection = get_db()

    profile = connection.execute(
        """
        SELECT *
        FROM profiles
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    connection.close()

    return profile


def save_profile(user_id: int, username: str | None, data: dict):
    today = date.today().isoformat()

    connection = get_db()

    connection.execute(
        """
        INSERT INTO profiles (
            user_id,
            username,
            name,
            age,
            city,
            gender,
            looking_for,
            interests,
            bio,
            photo_id,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(user_id)
        DO UPDATE SET
            username = excluded.username,
            name = excluded.name,
            age = excluded.age,
            city = excluded.city,
            gender = excluded.gender,
            looking_for = excluded.looking_for,
            interests = excluded.interests,
            bio = excluded.bio,
            photo_id = excluded.photo_id,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            username,
            data["name"],
            int(data["age"]),
            data["city"],
            data["gender"],
            data["looking_for"],
            data["interests"],
            data["bio"],
            data.get("photo_id"),
            today,
            today,
        ),
    )

    connection.commit()
    connection.close()


def delete_user_data(user_id: int):
    connection = get_db()

    connection.execute(
        "DELETE FROM profiles WHERE user_id = ?",
        (user_id,),
    )

    connection.execute(
        """
        DELETE FROM likes
        WHERE liker_id = ? OR liked_id = ?
        """,
        (user_id, user_id),
    )

    connection.execute(
        """
        DELETE FROM skips
        WHERE user_id = ? OR skipped_id = ?
        """,
        (user_id, user_id),
    )

    connection.execute(
        """
        DELETE FROM matches
        WHERE user1_id = ? OR user2_id = ?
        """,
        (user_id, user_id),
    )

    connection.commit()
    connection.close()


# ============================================================
# ПОИСК АНКЕТ
# ============================================================

def get_candidates(user_id: int):
    connection = get_db()

    candidates = connection.execute(
        """
        SELECT *
        FROM profiles

        WHERE user_id != ?
        AND age >= 18

        AND NOT EXISTS (
            SELECT 1
            FROM likes
            WHERE likes.liker_id = ?
            AND likes.liked_id = profiles.user_id
        )

        AND NOT EXISTS (
            SELECT 1
            FROM skips
            WHERE skips.user_id = ?
            AND skips.skipped_id = profiles.user_id
        )

        ORDER BY RANDOM()

        LIMIT 30
        """,
        (
            user_id,
            user_id,
            user_id,
        ),
    ).fetchall()

    connection.close()

    return candidates


# ============================================================
# VIBE-СОВМЕСТИМОСТЬ
# ============================================================

def calculate_vibe(me, other):
    score = 40

    # Один город
    if me["city"].strip().lower() == other["city"].strip().lower():
        score += 20

    # Подходит ли пол
    if me["looking_for"] == "Все":
        score += 15

    elif (
        me["looking_for"] == "Парни"
        and other["gender"] == "Парень"
    ):
        score += 15

    elif (
        me["looking_for"] == "Девушки"
        and other["gender"] == "Девушка"
    ):
        score += 15

    # Обратная совместимость
    if other["looking_for"] == "Все":
        score += 15

    elif (
        other["looking_for"] == "Парни"
        and me["gender"] == "Парень"
    ):
        score += 15

    elif (
        other["looking_for"] == "Девушки"
        and me["gender"] == "Девушка"
    ):
        score += 15

    # Совпадение интересов
    interests_me = {
        item.strip().lower()
        for item in me["interests"].split(",")
        if item.strip()
    }

    interests_other = {
        item.strip().lower()
        for item in other["interests"].split(",")
        if item.strip()
    }

    common_interests = interests_me & interests_other

    score += min(
        10,
        len(common_interests) * 3,
    )

    # Разница возраста
    age_difference = abs(
        me["age"] - other["age"]
    )

    score -= min(
        10,
        age_difference,
    )

    return max(
        0,
        min(100, score),
    )


# ============================================================
# ТЕКСТ АНКЕТЫ
# ============================================================

def profile_text(profile, vibe_score=None):
    text = (
        f"💜 <b>{profile['name']}, {profile['age']}</b>\n"
        f"📍 {profile['city']}\n"
        f"🎯 Ищет: {profile['looking_for']}\n"
        f"✨ Интересы: {profile['interests']}\n\n"
        f"📝 {profile['bio']}"
    )

    if vibe_score is not None:
        text += (
            f"\n\n🔥 <b>VIBE-сочетаемость: "
            f"{vibe_score}%</b>"
        )

    return text


# ============================================================
# КНОПКИ ПОД АНКЕТОЙ
# ============================================================

def candidate_keyboard(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❤️ Нравится",
                    callback_data=f"like:{user_id}",
                ),
                InlineKeyboardButton(
                    text="➡️ Дальше",
                    callback_data=f"skip:{user_id}",
                ),
            ]
        ]
    )


# ============================================================
# ПОКАЗ АНКЕТЫ
# ============================================================

async def send_profile_card(
    message: Message,
    profile,
    me,
):
    vibe_score = calculate_vibe(
        me,
        profile,
    )

    text = profile_text(
        profile,
        vibe_score,
    )

    keyboard = candidate_keyboard(
        profile["user_id"]
    )

    if profile["photo_id"]:
        await message.answer_photo(
            photo=profile["photo_id"],
            caption=text,
            reply_markup=keyboard,
        )

    else:
        await message.answer(
            text,
            reply_markup=keyboard,
        )


async def show_next_candidate(
    message: Message,
    user_id: int,
):
    me = get_profile(user_id)

    if not me:
        await message.answer(
            "Сначала создай анкету через /start."
        )
        return

    candidates = get_candidates(
        user_id
    )

    if not candidates:
        await message.answer(
            "😔 Новых анкет пока нет.\n\n"
            "Попробуй зайти позже.",
            reply_markup=main_keyboard,
        )
        return

    await send_profile_card(
        message,
        candidates[0],
        me,
    )


# ============================================================
# НАЧАЛО СОЗДАНИЯ АНКЕТЫ
# ============================================================

async def start_profile_creation(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    await state.set_state(
        ProfileForm.age_gate
    )

    age_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="✅ Мне 18 или больше"
                )
            ],
            [
                KeyboardButton(
                    text="❌ Мне меньше 18"
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await message.answer(
        "🔞 <b>Перед созданием анкеты</b>\n\n"
        "VIBE в этой версии предназначен "
        "только для пользователей 18+.\n\n"
        "Подтверди свой возраст:",
        reply_markup=age_keyboard,
    )


# ============================================================
# /START
# ============================================================

@dp.message(CommandStart())
async def start_handler(
    message: Message,
    state: FSMContext,
):
    profile = get_profile(
        message.from_user.id
    )

    if profile:

        await message.answer(
            f"💜 С возвращением, "
            f"<b>{profile['name']}</b>!\n\n"
            f"Выбери действие:",
            reply_markup=main_keyboard,
        )

    else:

        await start_profile_creation(
            message,
            state,
        )


# ============================================================
# ВОЗРАСТ
# ============================================================

@dp.message(
    ProfileForm.age_gate,
    F.text == "❌ Мне меньше 18",
)
async def underage_handler(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    await message.answer(
        "Спасибо за честный ответ.\n\n"
        "Эта версия VIBE доступна только 18+.",
        reply_markup=main_keyboard,
    )


@dp.message(
    ProfileForm.age_gate,
    F.text == "✅ Мне 18 или больше",
)
async def age_gate_handler(
    message: Message,
    state: FSMContext,
):
    await state.set_state(
        ProfileForm.name
    )

    await message.answer(
        "Отлично! 💜\n\n"
        "<b>1/8.</b> Как тебя зовут?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text="Отмена"
                    )
                ]
            ],
            resize_keyboard=True,
        ),
    )


@dp.message(ProfileForm.age_gate)
async def age_gate_wrong_handler(
    message: Message,
):
    await message.answer(
        "Нажми одну из кнопок выше 👆"
    )


# ============================================================
# ИМЯ
# ============================================================

@dp.message(
    ProfileForm.name,
    F.text,
)
async def profile_name_handler(
    message: Message,
    state: FSMContext,
):
    if message.text == "Отмена":

        await state.clear()

        await message.answer(
            "Создание анкеты отменено.",
            reply_markup=main_keyboard,
        )

        return

    name = message.text.strip()

    if not 2 <= len(name) <= 30:

        await message.answer(
            "Имя должно содержать "
            "от 2 до 30 символов."
        )

        return

    await state.update_data(
        name=name
    )

    await state.set_state(
        ProfileForm.age
    )

    await message.answer(
        "<b>2/8.</b> Сколько тебе лет?\n\n"
        "Введи число от 18 до 99."
    )


# ============================================================
# ВОЗРАСТ
# ============================================================

@dp.message(
    ProfileForm.age,
    F.text,
)
async def profile_age_handler(
    message: Message,
    state: FSMContext,
):
    try:
        age = int(
            message.text.strip()
        )

    except ValueError:

        await message.answer(
            "Напиши возраст числом.\n"
            "Например: 21"
        )

        return

    if not 18 <= age <= 99:

        await message.answer(
            "В этой версии VIBE "
            "можно создавать анкеты "
            "только с 18 лет."
        )

        return

    await state.update_data(
        age=age
    )

    await state.set_state(
        ProfileForm.city
    )

    await message.answer(
        "<b>3/8.</b> Из какого ты города?"
    )


# ============================================================
# ГОРОД
# ============================================================

@dp.message(
    ProfileForm.city,
    F.text,
)
async def profile_city_handler(
    message: Message,
    state: FSMContext,
):
    city = message.text.strip()

    if not 2 <= len(city) <= 50:

        await message.answer(
            "Напиши название города "
            "от 2 до 50 символов."
        )

        return

    await state.update_data(
        city=city
    )

    await state.set_state(
        ProfileForm.gender
    )

    await message.answer(
        "<b>4/8.</b> Какой у тебя пол?",
        reply_markup=gender_keyboard,
    )


# ============================================================
# ПОЛ
# ============================================================

@dp.message(
    ProfileForm.gender,
    F.text.in_(
        {
            "Парень",
            "Девушка",
            "Другое",
        }
    ),
)
async def profile_gender_handler(
    message: Message,
    state: FSMContext,
):
    await state.update_data(
        gender=message.text
    )

    await state.set_state(
        ProfileForm.looking_for
    )

    await message.answer(
        "<b>5/8.</b> Кого хочешь видеть "
        "в рекомендациях?",
        reply_markup=looking_keyboard,
    )


# ============================================================
# КОГО ИЩЕТ
# ============================================================

@dp.message(
    ProfileForm.looking_for,
    F.text.in_(
        {
            "Парни",
            "Девушки",
            "Все",
        }
    ),
)
async def profile_looking_handler(
    message: Message,
    state: FSMContext,
):
    await state.update_data(
        looking_for=message.text
    )

    await state.set_state(
        ProfileForm.interests
    )

    await message.answer(
        "<b>6/8.</b> Напиши свои интересы "
        "через запятую.\n\n"
        "Например:\n"
        "музыка, игры, спорт, кино, "
        "путешествия"
    )


# ============================================================
# ИНТЕРЕСЫ
# ============================================================

@dp.message(
    ProfileForm.interests,
    F.text,
)
async def profile_interests_handler(
    message: Message,
    state: FSMContext,
):
    interests = message.text.strip()

    if len(interests) < 2:

        await message.answer(
            "Добавь хотя бы один интерес."
        )

        return

    await state.update_data(
        interests=interests[:300]
    )

    await state.set_state(
        ProfileForm.bio
    )

    await message.answer(
        "<b>7/8.</b> Расскажи о себе "
        "в 1–3 предложениях."
    )


# ============================================================
# ОПИСАНИЕ
# ============================================================

@dp.message(
    ProfileForm.bio,
    F.text,
)
async def profile_bio_handler(
    message: Message,
    state: FSMContext,
):
    bio = message.text.strip()

    if not 5 <= len(bio) <= 500:

        await message.answer(
            "Описание должно быть "
            "от 5 до 500 символов."
        )

        return

    await state.update_data(
        bio=bio
    )

    await state.set_state(
        ProfileForm.photo
    )

    await message.answer(
        "<b>8/8.</b> Отправь фотографию 📸\n\n"
        "Или нажми «Пропустить».",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text="Пропустить"
                    )
                ]
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )


# ============================================================
# ФОТО
# ============================================================

@dp.message(
    ProfileForm.photo,
    F.photo,
)
async def profile_photo_handler(
    message: Message,
    state: FSMContext,
):
    photo_id = message.photo[-1].file_id

    await state.update_data(
        photo_id=photo_id
    )

    await show_profile_confirmation(
        message,
        state,
    )


@dp.message(
    ProfileForm.photo,
    F.text.casefold() == "пропустить",
)
async def profile_photo_skip_handler(
    message: Message,
    state: FSMContext,
):
    await state.update_data(
        photo_id=None
    )

    await show_profile_confirmation(
        message,
        state,
    )


# ============================================================
# ПРОВЕРКА АНКЕТЫ
# ============================================================

async def show_profile_confirmation(
    message: Message,
    state: FSMContext,
):
    data = await state.get_data()

    profile_preview = {
        "name": data["name"],
        "age": data["age"],
        "city": data["city"],
        "looking_for": data["looking_for"],
        "interests": data["interests"],
        "bio": data["bio"],
    }

    text = (
        "👀 <b>Проверь свою анкету:</b>\n\n"
        + profile_text(
            profile_preview
        )
        + "\n\n"
        "Всё правильно?"
    )

    await state.set_state(
        ProfileForm.confirm
    )

    await message.answer(
        text,
        reply_markup=confirm_keyboard,
    )


# ============================================================
# ПЕРЕСОЗДАНИЕ
# ============================================================

@dp.message(
    ProfileForm.confirm,
    F.text == "🔄 Заполнить заново",
)
async def restart_profile_handler(
    message: Message,
    state: FSMContext,
):
    await start_profile_creation(
        message,
        state,
    )


# ============================================================
# СОХРАНЕНИЕ АНКЕТЫ
# ============================================================

@dp.message(
    ProfileForm.confirm,
    F.text == "✅ Да, создать",
)
async def confirm_profile_handler(
    message: Message,
    state: FSMContext,
):
    data = await state.get_data()

    save_profile(
        user_id=message.from_user.id,
        username=message.from_user.username,
        data=data,
    )

    await state.clear()

    await message.answer(
        "🎉 <b>Анкета создана!</b>\n\n"
        "Теперь можно искать людей, "
        "ставить лайки и получать мэтчи. ❤️",
        reply_markup=main_keyboard,
    )


@dp.message(ProfileForm.confirm)
async def confirmation_wrong_handler(
    message: Message,
):
    await message.answer(
        "Выбери одну из кнопок ниже 👇",
        reply_markup=confirm_keyboard,
    )


# ============================================================
# МОЯ АНКЕТА
# ============================================================

@dp.message(F.text == "👤 Моя анкета")
async def my_profile_handler(
    message: Message,
):
    profile = get_profile(
        message.from_user.id
    )

    if not profile:

        await message.answer(
            "У тебя пока нет анкеты.\n\n"
            "Используй /start."
        )

        return

    text = profile_text(
        profile
    )

    if profile["photo_id"]:

        await message.answer_photo(
            profile["photo_id"],
            caption=text,
            reply_markup=main_keyboard,
        )

    else:

        await message.answer(
            text,
            reply_markup=main_keyboard,
        )


# ============================================================
# НАЙТИ ЧЕЛОВЕКА
# ============================================================

@dp.message(F.text == "🔥 Найти человека")
async def find_people_handler(
    message: Message,
):
    if not get_profile(
        message.from_user.id
    ):

        await message.answer(
            "Сначала создай анкету "
            "через /start."
        )

        return

    await show_next_candidate(
        message,
        message.from_user.id,
    )


# ============================================================
# ПРОПУСТИТЬ
# ============================================================

@dp.callback_query(
    F.data.startswith("skip:")
)
async def skip_handler(
    callback: CallbackQuery,
):
    user_id = callback.from_user.id

    target_id = int(
        callback.data.split(":")[1]
    )

    connection = get_db()

    connection.execute(
        """
        INSERT OR IGNORE INTO skips
        (user_id, skipped_id, created_at)
        VALUES (?, ?, ?)
        """,
        (
            user_id,
            target_id,
            date.today().isoformat(),
        ),
    )

    connection.commit()
    connection.close()

    await callback.answer(
        "Пропущено ➡️"
    )

    try:
        await callback.message.delete()

    except TelegramBadRequest:
        pass

    await show_next_candidate(
        callback.message,
        user_id,
    )


# ============================================================
# ЛАЙК
# ============================================================

@dp.callback_query(
    F.data.startswith("like:")
)
async def like_handler(
    callback: CallbackQuery,
):
    user_id = callback.from_user.id

    target_id = int(
        callback.data.split(":")[1]
    )

    if user_id == target_id:

        await callback.answer(
            "Нельзя поставить лайк себе 🙂",
            show_alert=True,
        )

        return

    connection = get_db()

    connection.execute(
        """
        INSERT OR IGNORE INTO likes
        (liker_id, liked_id, created_at)
        VALUES (?, ?, ?)
        """,
        (
            user_id,
            target_id,
            date.today().isoformat(),
        ),
    )

    reverse_like = connection.execute(
        """
        SELECT 1
        FROM likes
        WHERE liker_id = ?
        AND liked_id = ?
        """,
        (
            target_id,
            user_id,
        ),
    ).fetchone()

    is_match = reverse_like is not None

    if is_match:

        user1, user2 = sorted(
            [user_id, target_id]
        )

        connection.execute(
            """
            INSERT OR IGNORE INTO matches
            (user1_id, user2_id, created_at)
            VALUES (?, ?, ?)
            """,
            (
                user1,
                user2,
                date.today().isoformat(),
            ),
        )

    connection.commit()
    connection.close()

    await callback.answer(
        "❤️ Лайк отправлен!"
    )

    me = get_profile(
        user_id
    )

    other = get_profile(
        target_id
    )

    try:
        await callback.message.delete()

    except TelegramBadRequest:
        pass

    if is_match:

        score = calculate_vibe(
            me,
            other,
        )

        await callback.message.answer(
            f"💥 <b>МЭТЧ!</b>\n\n"
            f"Вы с <b>{other['name']}</b> "
            f"понравились друг другу! ❤️\n\n"
            f"🔥 VIBE-сочетаемость: "
            f"<b>{score}%</b>\n\n"
            f"Открой «💬 Мои знакомства»."
        )

        try:

            await bot.send_message(
                target_id,
                f"💥 <b>У тебя новый мэтч!</b>\n\n"
                f"Вы с <b>{me['name']}</b> "
                f"понравились друг другу! ❤️\n\n"
                f"🔥 VIBE-сочетаемость: "
                f"<b>{score}%</b>\n\n"
                f"Открой «💬 Мои знакомства».",
            )

        except Exception:
            pass

    else:

        await callback.message.answer(
            "❤️ Лайк отправлен!"
        )

    await show_next_candidate(
        callback.message,
        user_id,
    )


# ============================================================
# МОИ ЛАЙКИ
# ============================================================

@dp.message(F.text == "❤️ Мои лайки")
async def my_likes_handler(
    message: Message,
):
    user_id = message.from_user.id

    if not get_profile(user_id):

        await message.answer(
            "Сначала создай анкету."
        )

        return

    connection = get_db()

    sent = connection.execute(
        """
        SELECT profiles.*
        FROM likes

        JOIN profiles
        ON profiles.user_id = likes.liked_id

        WHERE likes.liker_id = ?

        ORDER BY likes.rowid DESC

        LIMIT 20
        """,
        (user_id,),
    ).fetchall()

    received = connection.execute(
        """
        SELECT profiles.*
        FROM likes

        JOIN profiles
        ON profiles.user_id = likes.liker_id

        WHERE likes.liked_id = ?

        ORDER BY likes.rowid DESC

        LIMIT 20
        """,
        (user_id,),
    ).fetchall()

    connection.close()

    text = "❤️ <b>Мои лайки</b>\n\n"

    text += "<b>Ты лайкнул:</b>\n"

    if sent:

        for profile in sent:

            text += (
                f"• {profile['name']}, "
                f"{profile['age']} — "
                f"{profile['city']}\n"
            )

    else:

        text += "Пока никого.\n"

    text += "\n<b>Тебя лайкнули:</b>\n"

    if received:

        for profile in received:

            text += (
                f"• {profile['name']}, "
                f"{profile['age']} — "
                f"{profile['city']}\n"
            )

    else:

        text += "Пока никто.\n"

    await message.answer(
        text
    )


# ============================================================
# МЭТЧИ
# ============================================================

@dp.message(F.text == "💬 Мои знакомства")
async def matches_handler(
    message: Message,
):
    user_id = message.from_user.id

    if not get_profile(user_id):

        await message.answer(
            "Сначала создай анкету."
        )

        return

    connection = get_db()

    matches = connection.execute(
        """
        SELECT profiles.*

        FROM matches

        JOIN profiles

        ON profiles.user_id =
            CASE
                WHEN matches.user1_id = ?
                THEN matches.user2_id

                ELSE matches.user1_id
            END

        WHERE matches.user1_id = ?
        OR matches.user2_id = ?

        ORDER BY matches.rowid DESC
        """,
        (
            user_id,
            user_id,
            user_id,
        ),
    ).fetchall()

    connection.close()

    if not matches:

        await message.answer(
            "💬 <b>Мэтчей пока нет.</b>\n\n"
            "Продолжай искать людей и "
            "ставить ❤️."
        )

        return

    me = get_profile(
        user_id
    )

    await message.answer(
        "💬 <b>Твои знакомства:</b>"
    )

    for profile in matches:

        score = calculate_vibe(
            me,
            profile,
        )

        if profile["username"]:

            contact = (
                f"@{profile['username']}"
            )

        else:

            contact = (
                f'<a href="tg://user?id='
                f'{profile["user_id"]}">'
                f'Открыть чат</a>'
            )

        await message.answer(
            f"💥 <b>{profile['name']}, "
            f"{profile['age']}</b>\n\n"
            f"📍 {profile['city']}\n"
            f"🔥 VIBE: <b>{score}%</b>\n\n"
            f"💬 {contact}"
        )


# ============================================================
# ЧЕЛОВЕК ДНЯ
# ============================================================

@dp.message(F.text == "🎲 Человек дня")
async def person_of_day_handler(
    message: Message,
):
    user_id = message.from_user.id

    me = get_profile(
        user_id
    )

    if not me:

        await message.answer(
            "Сначала создай анкету."
        )

        return

    connection = get_db()

    candidates = connection.execute(
        """
        SELECT *

        FROM profiles

        WHERE user_id != ?
        AND age >= 18

        AND NOT EXISTS (
            SELECT 1
            FROM skips
            WHERE skips.user_id = ?
            AND skips.skipped_id = profiles.user_id
        )

        AND NOT EXISTS (
            SELECT 1
            FROM likes
            WHERE likes.liker_id = ?
            AND likes.liked_id = profiles.user_id
        )
        """,
        (
            user_id,
            user_id,
            user_id,
        ),
    ).fetchall()

    connection.close()

    if not candidates:

        await message.answer(
            "🎲 Сегодня подходящих анкет нет."
        )

        return

    random_generator = random.Random(
        f"{date.today().isoformat()}:{user_id}"
    )

    person = random_generator.choice(
        candidates
    )

    await message.answer(
        "🎲 <b>Твой человек дня:</b>"
    )

    await send_profile_card(
        message,
        person,
        me,
    )


# ============================================================
# НАСТРОЙКИ
# ============================================================

@dp.message(F.text == "⚙️ Настройки")
async def settings_handler(
    message: Message,
):
    settings_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="✏️ Пересоздать анкету"
                )
            ],
            [
                KeyboardButton(
                    text="🗑 Удалить анкету"
                )
            ],
            [
                KeyboardButton(
                    text="⬅️ Назад"
                )
            ],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        "⚙️ <b>Настройки</b>",
        reply_markup=settings_keyboard,
    )


# ============================================================
# ПЕРЕСОЗДАНИЕ АНКЕТЫ
# ============================================================

@dp.message(
    F.text == "✏️ Пересоздать анкету"
)
async def edit_profile_handler(
    message: Message,
    state: FSMContext,
):
    await start_profile_creation(
        message,
        state,
    )


# ============================================================
# УДАЛЕНИЕ АНКЕТЫ
# ============================================================

@dp.message(
    F.text == "🗑 Удалить анкету"
)
async def delete_profile_handler(
    message: Message,
):
    delete_user_data(
        message.from_user.id
    )

    await message.answer(
        "🗑 <b>Анкета полностью удалена.</b>\n\n"
        "Все лайки, мэтчи и данные "
        "этого профиля тоже удалены.",
        reply_markup=main_keyboard,
    )


# ============================================================
# НАЗАД
# ============================================================

@dp.message(F.text == "⬅️ Назад")
async def back_handler(
    message: Message,
):
    await message.answer(
        "Главное меню:",
        reply_markup=main_keyboard,
    )


# ============================================================
# НЕИЗВЕСТНОЕ СООБЩЕНИЕ
# ============================================================

@dp.message()
async def unknown_message_handler(
    message: Message,
):
    await message.answer(
        "🤔 Я не понял эту команду.\n\n"
        "Используй кнопки главного меню.",
        reply_markup=main_keyboard,
    )


# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    logging.basicConfig(
        level=logging.INFO
    )

    init_db()

    print("💜 VIBE BOT запущен!")

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    asyncio.run(main())