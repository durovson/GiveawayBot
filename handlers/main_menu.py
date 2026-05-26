from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
import html
from database import db
from loader import ADMIN_IDS
from handlers.giveaway_creation import GiveawayCreation
from utils import is_admin, is_any_admin, safe_answer, safe_edit_text

router = Router()

async def get_main_menu_keyboard(user_id: int):
    builder = InlineKeyboardBuilder()
    
    if user_id in ADMIN_IDS:
        # Admin Menu
        builder.button(text="Game", callback_data="game_menu", icon_custom_emoji_id="5422626434331990897")
        builder.button(text="Giveaway", callback_data="create_giveaway", icon_custom_emoji_id="5258185631355378853")
        builder.button(text="History", callback_data="history_created", icon_custom_emoji_id="5257969839313526622")
        builder.button(text="OTC", callback_data="otc_market", icon_custom_emoji_id="5258204546391351475")
        builder.button(text="Notifications", callback_data="manage_notifications", icon_custom_emoji_id="5260325873688518261")
        builder.button(text="Support", url="https://t.me/ton_geist", icon_custom_emoji_id="5258093637450866522")

        if user_id == 786080766:
            builder.button(text="Update GIF", callback_data="admin_update_gif")
            builder.adjust(1, 2, 2, 1, 1)
        else:
            builder.adjust(1, 2, 2, 1)
    else:
        # User Menu
        builder.button(text="Game", callback_data="game_menu", icon_custom_emoji_id="5422626434331990897")
        builder.button(text="Support", url="https://t.me/ton_geist", icon_custom_emoji_id="5258093637450866522")
        builder.button(text="OTC", callback_data="otc_market", icon_custom_emoji_id="5258204546391351475")
        builder.adjust(2, 1)

    return builder.as_markup()

MAIN_MENU_TEXT = (
    "<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji><b>NOTAPES | SYSTEM</b><tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>\n\n"
    "<blockquote>Here you can:\n\n"
    "• Participate in giveaways\n"
    "• Connect your wallet\n"
    "• Create OTC ads</blockquote>\n\n"
    "<b>Ready to get started? Select the desired section from the menu:</b>"
)

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext, command: CommandObject):
    args = command.args
    await state.clear()

    if args:
        # Handle deep-linking (e.g. start=join_123)
        if args.startswith("join_"):
            try:
                giveaway_id = int(args.split("_")[1])
                # We can manually trigger the join callback logic or just show the menu.
                # For now, let's proceed to menu but we have the ID if needed.
                pass
            except:
                pass

    await safe_answer(
        message,
        MAIN_MENU_TEXT,
        reply_markup=await get_main_menu_keyboard(message.from_user.id),
        parse_mode=ParseMode.HTML, state=state)

@router.message(Command("setup"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_setup(message: types.Message):
    if await is_admin(message.chat.id, message.from_user.id):
        await db.track_chat(message.chat.id, message.chat.title, message.chat.type)
        safe_title = html.escape(message.chat.title)
        await safe_answer(
            message,
            f"<tg-emoji emoji-id=\"5258501105293205250\">👏</tg-emoji> Group <b>{safe_title}</b> successfully registered!\n\n"
            "<blockquote>Now you can create giveaways in it via private messages with the bot.</blockquote>",
            parse_mode=ParseMode.HTML, state=state)
    else:
        await safe_answer(message, "<tg-emoji emoji-id=\"5273876254989246882\">🤬</tg-emoji> <b>This command can only be executed by a group administrator.</b>", state=state)

@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await safe_edit_text(
        callback,
        MAIN_MENU_TEXT,
        reply_markup=await get_main_menu_keyboard(callback.from_user.id),
        parse_mode=ParseMode.HTML, state=state)

@router.callback_query(F.data == "create_giveaway")
async def create_giveaway_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    chats = await db.get_tracked_groups()
    if not chats:
        await safe_edit_text(callback, "<tg-emoji emoji-id=\"5273876254989246882\">🤬</tg-emoji> <b>There are no available groups. Add the bot to the group and make it an administrator.</b>", state=state)
        return

    admin_chats = []
    for chat in chats:
        if await is_admin(chat['chat_id'], callback.from_user.id):
            admin_chats.append(chat)

    if not admin_chats:
        await callback.answer("❌ You do not have administrator rights in connected chats.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for chat in admin_chats:
        builder.button(text=chat['title'], callback_data=f"chat_{chat['chat_id']}")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    msg = await safe_edit_text(callback, "Select a group to hold the giveaway:", reply_markup=builder.as_markup(), state=state)
    await state.update_data(last_msg_id=msg.message_id)
    await state.set_state(GiveawayCreation.SELECT_CHAT)
