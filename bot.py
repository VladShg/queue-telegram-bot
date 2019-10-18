from apscheduler.schedulers.asyncio import AsyncIOScheduler
import re
import sys

from aiogram import Bot, Dispatcher, executor
from aiogram.types import InlineQuery, Message, User as TelegramUser, \
    InputTextMessageContent, InlineQueryResultArticle, \
    InlineKeyboardButton, InlineKeyboardMarkup, \
    CallbackQuery

from database import Session, Chat, QueueRecord, Queue, User
from datetime import datetime, timedelta
from config import token

bot = Bot(token=token)
dp = Dispatcher(bot)


def get_user(session, user: TelegramUser):
    db_user = session.query(User).filter(User.id == user.id).first()
    if not db_user:
        db_user = User(id=user.id, user_name=user.full_name, username=user.username)
        session.add(db_user)
    else:
        db_user.user_name = user.full_name
        db_user.username = user.username
    session.commit()
    return db_user


def get_chat(session, chat_id):
    chat = session.query(Chat).filter(Chat.chat_id == chat_id).first()
    if not chat:
        chat = Chat(chat_id=chat_id, default_time=60, pin=True)
        session.add(chat)
    return chat


def get_keyboard(queue):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Join", callback_data=f"add-{queue.id}"))
    keyboard.add(InlineKeyboardButton("Leave", callback_data=f"del-{queue.id}"))
    return keyboard


def is_reply_queue(message: Message):
    if message.reply_to_message == None:
        return False
    session = Session()
    queue = session.query(Queue).filter(Queue.message_id == message.reply_to_message.message_id).first()
    if not queue:
        session.close()
        return False
    session.close()
    return True

# /help
@dp.message_handler(commands=["help"])
async def info_handler(message: Message):
    session = Session()
    chat = get_chat(session, message.chat.id)
    chat_pin = "[✅ On]" if chat.pin else "[❌ Off]"
    text = "List of commands:" \
           "\n/create [text] - create queue." \
           f"\n/timer [mins] - set time between creation and publication [{chat.default_time} minutes]." \
           f"\n/pin - pin message (with notification) {chat_pin}." \
           f"\n(notification is enabled by default)" \
           f"\n\nIn order to add another user to queue reply to queue message with user's @username. " \
           f"User must use the bot previously at least once(must be saved in database)"

    session.commit()
    await message.reply(text, reply=False)

# /pin
@dp.message_handler(commands=["pin"])
async def pin_switch_handler(message: Message):
    session = Session()
    chat = get_chat(session, message.chat.id)
    chat.pin = not chat.pin
    session.commit()
    if chat.pin:
        await message.reply("Pin enabled", reply=False)
    else:
        await message.reply("Pin disabled", reply=False)
    session.close()


# /timer
@dp.message_handler(text="/timer")
async def timer_empty_handler(message: Message):
    session = Session()
    chat = get_chat(session, message.chat.id)
    time = chat.default_time
    session.commit()
    session.close()
    await message.reply(f"Times: {time} minutes", reply=False)

# /timer [mins]
@dp.message_handler(commands=["timer"])
async def timer_handler(message: Message):

    def check_int(number):
        return bool(re.match("^[-+]?[0-9]+$", number))

    arg = message.text.split(' ')
    if len(arg) < 2 or arg[1].replace(' ', '') == '' or check_int(arg[1]) is False:
        await message.reply("Incorrect input\n"
                            "/timer [mins], mins >= 0, mins <= sys.maxint", reply=False)
        return
    if sys.maxsize <= int(arg[1]):
        await message.reply("Number should not be larger than int", reply=False)
        return
    if int(arg[1]) < 0:
        await message.reply("Number should not be less than 0", reply=False)
        return

    session = Session()
    chat = get_chat(session, message.chat.id)
    chat.default_time = int(arg[1])
    session.commit()
    session.close()

    await message.reply(f"Timer is set to {int(arg[1])} minutes", reply=False)


# /create [title]
@dp.message_handler(commands=["create"])
async def create_handler(message: Message):
    title = message.text[8:]
    if title.replace(" ", "") == "":
        await message.reply("Empty title. Use /create [text]\n",
                            reply=False)
        return
    if len(title) >= 3500:
        await message.reply("Title should not be longer than 3500 symbols",
                            reply=False)
        return
    session = Session()
    time = datetime.now()
    chat = get_chat(session, message.chat.id)
    delta = timedelta(minutes=chat.default_time)
    time += delta

    message_bot = await message.reply(f"{title}\n\nPublication time: {time.strftime('%H:%M, %d.%m.%Y')}",
                                      reply=False)

    queue = Queue(creator_id=message.from_user.id, message_id=message_bot.message_id,
                  pin_date=time, title=title, chat_id=message.chat.id)
    session.add(queue)
    session.commit()
    session.close()

# /delete
@dp.message_handler(lambda msg: msg.reply_to_message is not None, commands=["/delete"])
async def delete_handler(message: Message):
    pass
    session = Session()
    queue = session.query(Queue).filter(Queue.chat_id == message.chat.id,
                                        Queue.message_id == message.reply_to_message.message_id).first()
    if queue.creator_id != message.from_user.id:
        await message.reply("Право закрыть очередь есть только у создателя")
        session.close()
        return
    else:
        if queue.is_pinned is False:
            await message.reply(f"{queue.title} closed. Publication on saved time is canceled", reply=False)
            session.delete(queue)
            session.commit()
            session.close()
        else:
            await message.reply(f"{queue.title} Closed. Message and line deleted", reply=False)
            await bot.delete_message(queue.chat_id, queue.message_id)
            session.query(QueueRecord).filter(QueueRecord.queue_id == queue.id).delete()
            session.delete(queue)
            session.commit()
            session.close()

    await message.reply("Only creator can close the queue", reply=False)

# reply @username on queue message
@dp.message_handler(lambda msg: is_reply_queue(msg))
async def queue_reply_handler(message: Message):
    username = message.text
    if "@" not in username or len(username) >= 3500:
        await message.reply("Wrong `@username` or message is too long")
        return
    username_plain = username.replace("@", "")
    session = Session()
    __ = get_user(session, message.from_user)  # update sender obj
    user = session.query(User).filter(User.username == username_plain).first()
    if not user:
        session.close()
        await message.reply(f"`{username}` is not found.", parse_mode="Markdown")
        return
    queue = session.query(Queue).filter(Queue.message_id == message.reply_to_message.message_id).one()
    record = session.query(QueueRecord).filter(QueueRecord.user_id == user.id, QueueRecord.queue_id == queue.id).first()
    if record:
        session.close()
        await message.reply(f"`{username}` is already in the list.", parse_mode="Markdown")
        return
    if len(session.query(QueueRecord).filter(QueueRecord.creator_id == message.from_user.id).all()) >= 1:
        session.close()
        await message.reply("You cant add more than 1 user")
        return
    position = len(session.query(QueueRecord).filter(QueueRecord.queue_id == queue.id).all()) + 1
    session.add(QueueRecord(queue_id=queue.id, creator_id=message.from_user.id, user_id=user.id, position=position))
    session.commit()

    text = f"{queue.title}\n\nLine:"
    for record in session.query(QueueRecord).filter(QueueRecord.queue_id == queue.id).all():
        text += f"\n{record.position}. {record.user.user_name}"

    await bot.edit_message_text(text, queue.chat_id, queue.message_id, reply_markup=get_keyboard(queue))

    session.commit()
    session.close()

    await message.reply("User added")

# [ Записаться ]
@dp.callback_query_handler(lambda callback: "add" in callback.data)
async def callback_add_handler(callback: CallbackQuery):
    queue_id = int(callback.data.split("-")[1])
    session = Session()
    record = session.query(QueueRecord).filter(QueueRecord.queue_id == queue_id,
                                               QueueRecord.user_id == callback.from_user.id).first()
    if record:
        session.close()
        await bot.answer_callback_query(callback.id, "You are already in the list")
        return

    queue = session.query(Queue).filter(Queue.id == queue_id).first()
    position = len(session.query(QueueRecord).filter(QueueRecord.queue_id == queue_id).all()) + 1
    user = get_user(session, callback.from_user)
    session.add(QueueRecord(queue_id=queue_id, user_id=callback.from_user.id, position=position))
    session.commit()

    text = f"{queue.title}\n\nLine:"
    for record in session.query(QueueRecord).filter(QueueRecord.queue_id == queue_id).all():
        text += f"\n{record.position}. {record.user.user_name}"

    await bot.answer_callback_query(callback.id, "Entered")
    await bot.edit_message_text(text, queue.chat_id, queue.message_id, reply_markup=get_keyboard(queue))
    session.close()

# [ Выписаться ]
@dp.callback_query_handler(lambda callback: "del" in callback.data)
async def callback_del_handler(callback: CallbackQuery):
    queue_id = int(callback.data.split("-")[1])
    session = Session()
    record = session.query(QueueRecord).filter(QueueRecord.queue_id == queue_id,
                                               QueueRecord.user_id == callback.from_user.id).first()
    if not record:
        session.close()
        await bot.answer_callback_query(callback.id, "You are not in the list")
        return

    user = get_user(session, callback.from_user)
    queue = session.query(Queue).filter(Queue.id == queue_id).first()
    record.remove_record()
    session.commit()

    text = f"{queue.title}\n\nLine:"
    for record in session.query(QueueRecord).filter(QueueRecord.queue_id == queue_id).all():
        text += f"\n{record.position}. {record.user.user_name}"

    await bot.answer_callback_query(callback.id, "Left the line")
    await bot.edit_message_text(text, queue.chat_id, queue.message_id, reply_markup=get_keyboard(queue))
    session.close()


async def check_queue():
    session = Session()
    # queues = session.query(Queue).filter(Queue.is_pinned is False, Queue.pin_date < datetime.now()).all()
    queues = session.query(Queue).filter(Queue.is_pinned == False, Queue.pin_date < datetime.now()).all()

    for queue in queues:
        try:
            chat = get_chat(session, queue.chat_id)
            message = await bot.send_message(queue.chat_id,
                                             f"{queue.title}\n\nLine:", reply_markup=get_keyboard(queue))
            try:
                if chat.pin:
                    await bot.pin_chat_message(queue.chat_id, message.message_id)
            except Exception as e:
                await bot.send_message(queue.chat_id, "Not enough rights for the pin")

            queue.is_pinned = True
            queue.message_id = message.message_id
            session.commit()
        except Exception as e:
            print(e)


if __name__ == '__main__':
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_queue, "interval", seconds=15, max_instances=1, coalesce=True)
    scheduler.start()

    executor.start_polling(dp)
