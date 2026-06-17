import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.formatting import Bold, Text, TextLink

from miniflux_bot.gateway import MinifluxGateway
from miniflux_bot.models import Entry
from miniflux_bot.notifier import Notifier, TransientNotifierException


class EntryActionCallbackData(CallbackData, prefix="entry"):
    action: str
    id: int


@dataclass
class EntryAction:
    key: str
    display_name: str
    style: str | None = None

    def generate_button(self, entry_id: int) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=self.display_name,
            callback_data=EntryActionCallbackData(
                action=self.key,
                id=entry_id,
            ).pack(),
            style=self.style,
        )


class TelegramBot(Notifier):
    def __init__(self, token: str, chat_id: int, gateway: MinifluxGateway) -> None:
        self._bot = Bot(
            token=token, default=DefaultBotProperties(disable_notification=True)
        )
        self._chat_id = chat_id
        self._gateway = gateway
        self._dp = Dispatcher()
        self._dp.callback_query(EntryActionCallbackData.filter())(self._on_action)
        self._actions: dict[str, EntryAction] = {
            "delete": EntryAction(key="delete", display_name="Delete", style="danger"),
            "read": EntryAction(key="read", display_name="Read", style="success"),
            "unread": EntryAction(key="unread", display_name="Unread", style="primary"),
        }

    def _generate_keyboard(
        self, entry_id: int, actions: list[str]
    ) -> InlineKeyboardMarkup:
        buttons = [
            [self._actions[action].generate_button(entry_id) for action in actions]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    async def notify(self, entry: Entry) -> None:
        content = Text(
            Bold(entry.feed_title),
            " - ",
            TextLink(entry.title, url=entry.url),
        )
        keyboard = self._generate_keyboard(
            entry_id=entry.id,
            actions=["read", "delete"],
        )
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                **content.as_kwargs(),
                reply_markup=keyboard,
            )
        except TelegramRetryAfter as exc:
            raise TransientNotifierException(
                str(exc), retry_after=exc.retry_after
            ) from exc
        except (TelegramNetworkError, TelegramServerError) as exc:
            raise TransientNotifierException(str(exc)) from exc

    async def _on_action(
        self, callback: CallbackQuery, callback_data: EntryActionCallbackData
    ) -> None:
        entry_id = callback_data.id
        action = callback_data.action
        message = callback.message

        if message is None:
            await callback.answer("Message no longer available")
            return

        answered = False
        try:
            logging.info(
                "Get action for message: id=%d, action=%s, entry_id=%d",
                message.chat.id,
                action,
                entry_id,
            )
            match action:
                case "delete":
                    await self._gateway.mark_read(entry_id)
                    await self._bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=message.message_id,
                    )
                case "read" | "unread":
                    match action:
                        case "read":
                            toggled = "unread"
                            await self._gateway.mark_read(entry_id)
                        case "unread":
                            toggled = "read"
                            await self._gateway.mark_unread(entry_id)

                    keyboard = self._generate_keyboard(
                        entry_id=entry_id, actions=[toggled, "delete"]
                    )

                    await self._bot.edit_message_reply_markup(
                        chat_id=message.chat.id,
                        message_id=message.message_id,
                        reply_markup=keyboard,
                    )

        except TelegramBadRequest as exc:
            logging.exception(
                "Action '%s' failed with: %s", action, exc, exc_info=False
            )
            if not answered:
                await callback.answer(
                    f"Action '{action}' failed with: {exc}", show_alert=True
                )
                answered = True
            return

        finally:
            if not answered:
                await callback.answer()

    async def run(self) -> None:
        await self._dp.start_polling(self._bot, handle_signals=False)
