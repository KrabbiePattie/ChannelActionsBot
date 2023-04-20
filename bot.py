# @ChannelActionsBot
# (c) @xditya.

import contextlib
import re
import logging

from redis import Redis
from decouple import config
from telethon import TelegramClient, events, Button, types, functions, errors

logging.basicConfig(
    level=logging.INFO, format="[%(levelname)s] %(asctime)s - %(message)s"
)
log = logging.getLogger("ChannelActions")
log.info("\n\nStarting...\n")


try:
    bot_token = config("BOT_TOKEN")
    REDIS_URI = config("REDIS_URI")
    REDIS_PASSWORD = config("REDIS_PASSWORD")
    AUTH = [int(i) for i in config("OWNERS").split(" ")]
except Exception as e:
    log.exception(e)
    exit(1)

# connecting the client
try:
    bot = TelegramClient(None, 6, "eb06d4abfb49dc3eeb1aeb98ae0f581e").start(
        bot_token=bot_token
    )
except Exception as e:
    log.exception(e)
    exit(1)

REDIS_URI = REDIS_URI.split(":")
db = Redis(
    host=REDIS_URI[0],
    port=REDIS_URI[1],
    password=REDIS_PASSWORD,
    decode_responses=True,
)

# users to db
def str_to_list(text):  # Returns List
    return text.split(" ")


def list_to_str(list):  # Returns String  # sourcery skip: avoid-builtin-shadow
    str = "".join(f"{x} " for x in list)
    return str.strip()


def is_added(var, id):  # Take int or str with numbers only , Returns Boolean
    if not str(id).isdigit():
        return False
    users = get_all(var)
    return str(id) in users


def add_to_db(var, id):  # Take int or str with numbers only , Returns Boolean
    # sourcery skip: avoid-builtin-shadow
    id = str(id)
    if not id.isdigit():
        return False
    try:
        users = get_all(var)
        users.append(id)
        db.set(var, list_to_str(users))
        return True
    except Exception as e:
        return False


def get_all(var):  # Returns List
    users = db.get(var)
    return [""] if users is None or users == "" else str_to_list(users)


async def get_me():
    me = await bot.get_me()
    myname = me.username
    return f"@{myname}"


bot_username = bot.loop.run_until_complete(get_me())
start_msg = """Hi {user}!

**I'm a channel actions bot, mainly focused on working with the new [Admin Approval Invite Links](https://t.me/telegram/153).**

**__I can__**:
- __Auto Approve New Join Requests.__
- __Auto Decline New Join Requests.__

`Click the below button to know how to use me!`"""
start_buttons = [
    [Button.inline("HOW TO USE ME ❓", data="helper")],
    [Button.url("UPDATES CHANNEL", "https://t.me/FlixBots")],
]


@bot.on(events.NewMessage(incoming=True, pattern=f"^/start({bot_username})?$"))
async def starters(event):
    if not is_added("BOTUSERS", event.sender_id):
        add_to_db("BOTUSERS", event.sender_id)
    from_ = await bot.get_entity(event.sender_id)
    await event.reply(
        start_msg.format(user=from_.first_name),
        buttons=start_buttons,
        link_preview=False,
    )


@bot.on(events.CallbackQuery(data="start"))
async def start_in(event):
    from_ = await bot.get_entity(event.sender_id)
    await event.edit(
        start_msg.format(user=from_.first_name),
        buttons=start_buttons,
        link_preview=False,
    )


@bot.on(events.CallbackQuery(data="helper"))
async def helper(event):
    await event.edit(
        '**Usage instructions.**\n\nAdd me to your channel, as administrator, with "add users" permission, and forward me a message from that chat to set me up!\n\nTo approve members who are already in waiting list, upgrade to premium for 3$ per month! Contact @Iggie if interested.',
        buttons=Button.inline("Main Menu 📭", data="start"),
    )


@bot.on(events.NewMessage(incoming=True, func=lambda e: e.is_private and e.fwd_from))
async def settings_selctor(event):  # sourcery skip: avoid-builtin-shadow
    id = event.fwd_from.from_id
    if not isinstance(id, types.PeerChannel):
        await event.reply("Looks like this isn't from a channel!")
        return
    try:
        chat = await bot.get_entity(id)
        if chat.admin_rights is None:
            await event.reply("Seems like I'm not admin in this channel!")
            return
    except ValueError:
        await event.reply("Seems like you haven't added me to your channel!")
        return

    # check if the guy trying to change settings is an admin

    try:
        who_u = (
            await bot(
                functions.channels.GetParticipantRequest(
                    channel=chat.id,
                    participant=event.sender_id,
                )
            )
        ).participant
    except errors.rpcerrorlist.UserNotParticipantError:
        await event.reply(
            "You are not in the channel, or an admin, to perform this action."
        )
        return
    if not (
        isinstance(
            who_u, (types.ChannelParticipantCreator, types.ChannelParticipantAdmin)
        )
    ):
        await event.reply(
            "You are not an admin of this channel and cannot change it's settings!"
        )
        return

    added_chats = db.get("CHAT_SETTINGS") or "{}"
    added_chats = eval(added_chats)
    setting = added_chats.get(str(chat.id)) or "Auto-Approve"
    await event.reply(
        "**Settings for {title}**\n\nSelect what to do on new join requests.\n\n**Current setting** - __{set}__".format(
            title=chat.title, set=setting
        ),
        buttons=[
            [Button.inline("Auto-Approve", data=f"set_ap_{chat.id}")],
            [Button.inline("Auto-Disapprove", data=f"set_disap_{chat.id}")],
        ],
    )


@bot.on(events.CallbackQuery(data=re.compile("set_(.*)")))
async def settings(event):
    args = event.pattern_match.group(1).decode("utf-8")
    setting, chat = args.split("_")
    added_chats = db.get("CHAT_SETTINGS") or "{}"
    added_chats = eval(added_chats)
    if setting == "ap":
        op = "Auto-Approve"
        added_chats.update({chat: op})
    elif setting == "disap":
        op = "Auto-Disapprove"
        added_chats.update({chat: op})
    db.set("CHAT_SETTINGS", str(added_chats))
    await event.edit(
        f"Settings updated! New members in the channel `{chat}` will be {op}d!"
    )


@bot.on(events.Raw(types.UpdateBotChatInviteRequester))
async def approver(event):
    chat = event.peer.channel_id
    chat_settings = db.get("CHAT_SETTINGS") or "{}"
    chat_settings = eval(chat_settings)
    welcome_msg = eval(await db.get("WELCOME_MSG") or "{}")
    chat_welcome = (
        welcome_msg.get(chat)
        or "Hello {name}, your request to join {chat} has been {dn}"
    )
    chat_welcome += "\nSend /start to know more."  # \n\n__**Powered by @Flixbots**__"
    who = await bot.get_entity(event.user_id)
    chat_ = await bot.get_entity(chat)
    dn = "approved!"
    appr = True
    if chat_settings.get(str(chat)) == "Auto-Approve":
        appr = True
        dn = "approved!"
    elif chat_settings.get(str(chat)) == "Auto-Disapprove":
        appr = False
        dn = "disapproved :("
    with contextlib.suppress(
        errors.rpcerrorlist.UserIsBlockedError, errors.rpcerrorlist.PeerIdInvalidError
    ):
        await bot.send_message(
            event.user_id,
            chat_welcome.format(name=who.first_name, chat=chat_.title, dn=dn),
            buttons = [
               [Button.url("⏩ FREE PREMIUM NETFLIX ACCOUNTS ⏪", url="https://t.me/+xQqr07Os-AdmNjY0")],
               [Button.url("⚠ DOWNLOAD WHATSAPP SPY APP FOR FREE ⚠", url="https://t.me/+xQqr07Os-AdmNjY0")],
            ] 
        )   
    with contextlib.suppress(errors.rpcerrorlist.UserAlreadyParticipantError):
        await bot(
            functions.messages.HideChatJoinRequestRequest(
                approved=appr, peer=chat, user_id=event.user_id
            )
        )


@bot.on(events.NewMessage(incoming=True, from_users=AUTH, pattern="^/stats$"))
async def auth_(event):
    t = db.get("CHAT_SETTINGS") or "{}"
    t = eval(t)
    await event.reply(
        "**ChannelActionsBot Stats**\n\nUsers: {}\nGroups added (with modified settings): {}".format(
            len(get_all("BOTUSERS")), len(t.keys())
        )
    )


@bot.on(events.NewMessage(incoming=True, from_users=AUTH, pattern="^/broadcast$"))
async def broad(e):
    if not e.reply_to_msg_id:
        return await e.reply(
            "Please use `/broadcast` as reply to the message you want to broadcast."
        )
    msg = await e.get_reply_message()
    xx = await e.reply("In progress...")
    users = get_all("BOTUSERS")
    done = error = 0
    for i in users:
        try:
            await bot.send_message(
                int(i),
                msg.text,
                file=msg.media,
                buttons=msg.buttons,
                link_preview=False,
            )
            done += 1
        except Exception:
            error += 1
    await xx.edit("Broadcast completed.\nSuccess: {}\nFailed: {}".format(done, error))


log.info("Started Bot - %s", bot_username)
log.info("\n@FlixBots\n\nBy - @Iggie.")

bot.run_until_disconnected()
