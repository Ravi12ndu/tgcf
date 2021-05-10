import logging

from telethon import TelegramClient, events

from tgcf import config
from tgcf.bot import (
    forward_command_handler,
    help_command_handler,
    remove_command_handler,
    start_command_handler,
)
from tgcf.plugins import apply_plugins
from tgcf.utils import send_message

KEEP_LAST_MANY = 10000

existing_hashes = []

_stored = {}


class EventUid:
    def __init__(self, event):
        self.chat_id = event.chat_id
        try:
            self.msg_id = event.id
        except:
            self.msg_id = event.deleted_id

    def __str__(self):
        return f"chat={self.chat_id} msg={self.msg_id}"

    def __eq__(self, other):
        return self.chat_id == other.chat_id and self.msg_id == other.msg_id

    def __hash__(self) -> int:
        return hash(self.__str__())


async def new_message_handler(event):
    chat_id = event.chat_id

    if chat_id not in config.from_to:
        return
    logging.info(f"New message received in {chat_id}")
    message = event.message

    global _stored

    event_uid = EventUid(event)

    length = len(_stored)
    exceeding = length - KEEP_LAST_MANY

    if exceeding > 0:
        for key in _stored:
            del _stored[key]
            break

    to_send_to = config.from_to.get(chat_id)

    if to_send_to:
        if event_uid not in _stored:
            _stored[event_uid] = []

        message = apply_plugins(message)
        if not message:
            return
        for recipient in to_send_to:
            fwded_msg = await send_message(event.client, recipient, message)
            _stored[event_uid].append(fwded_msg)

    existing_hashes.append(hash(message.text))


async def edited_message_handler(event):
    message = event.message

    chat_id = event.chat_id

    if chat_id not in config.from_to:
        return

    logging.info(f"Message edited in {chat_id}")

    event_uid = EventUid(event)

    message = apply_plugins(message)

    if not message:
        return

    fwded_msgs = _stored.get(event_uid)

    if fwded_msgs:
        for msg in fwded_msgs:
            if config.CONFIG.live.delete_on_edit == message.text:
                await msg.delete()
                await message.delete()
            else:
                await msg.edit(message.text)
        return

    to_send_to = config.from_to.get(event.chat_id)

    for recipient in to_send_to:
        await send_message(event.client, recipient, message)


async def deleted_message_handler(event):
    chat_id = event.chat_id
    if chat_id not in config.from_to:
        return

    logging.info(f"Message deleted in {chat_id}")

    event_uid = EventUid(event)
    fwded_msgs = _stored.get(event_uid)
    if fwded_msgs:
        for msg in fwded_msgs:
            await msg.delete()
        return


ALL_EVENTS = {
    "start": (start_command_handler, events.NewMessage(pattern="/start")),
    "forward": (forward_command_handler, events.NewMessage(pattern="/forward")),
    "remove": (remove_command_handler, events.NewMessage(pattern="/remove")),
    "help": (help_command_handler, events.NewMessage(pattern="/help")),
    "new": (new_message_handler, events.NewMessage()),
    "edited": (edited_message_handler, events.MessageEdited()),
    "deleted": (deleted_message_handler, events.MessageDeleted()),
}


def start_sync():
    client = TelegramClient(config.SESSION, config.API_ID, config.API_HASH)
    for key, val in ALL_EVENTS.items():
        if config.CONFIG.live.delete_sync is False and key == "deleted":
            continue
        client.add_event_handler(*val)
        logging.info(f"Added event handler for {key}")
    client.start()
    client.run_until_disconnected()
