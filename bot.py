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
    keyboard.add(InlineKeyboardButton("Записаться", callback_data=f"add-{queue.id}"))
    keyboard.add(InlineKeyboardButton("Выписаться", callback_data=f"del-{queue.id}"))
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
    chat_pin = "[✅ Включено]" if chat.pin else "[❌ Отключено]"
    text = "Список команд:" \
           "\n/create [text] - создать очередь." \
           "\n/delete - удалить очередь(ответить на сообщение бота о создании или " \
           "планировании публикации, право на удаление есть только у создателя)." \
           f"\n/timer [mins] - установить время между созданием очереди и пином [{chat.default_time} минут]." \
           f"\n/pin - пин (с уведомлением) {chat_pin}." \
           f"\n(если уведомление не пришло, проблемы телеграма, а не бота)" \
           f"\n\nЧто бы записать другого человека в очередь, нужно ответить на сообщение бота с его @юзернеймом. " \
           f"Этот человек должен хотя бы раз использовать очередь со своего аккаунта(быть записаным в базу данных)"

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
        await message.reply("Пин включен", reply=False)
    else:
        await message.reply("Пин выключен", reply=False)
    session.close()

# /timer
@dp.message_handler(text="/timer")
async def timer_empty_handler(message: Message):
    session = Session()
    chat = get_chat(session, message.chat.id)
    time = chat.default_time
    session.commit()
    session.close()
    await message.reply(f"Таймер: {time} минут", reply=False)

# /timer [mins]
@dp.message_handler(commands=["timer"])
async def timer_handler(message: Message):

    def check_int(number):
        return bool(re.match("^[-+]?[0-9]+$", number))

    arg = message.text.split(' ')
    if len(arg) < 2 or arg[1].replace(' ', '') == '' or check_int(arg[1]) is False:
        await message.reply("Некорректный ввод\n"
                            "/timer [mins], mins >= 0, mins <= sys.maxint", reply=False)
        return
    if sys.maxsize <= int(arg[1]):
        await message.reply("Число не может быть больше int", reply=False)
        return
    if int(arg[1]) < 0:
        await message.reply("Число не может быть меньше нуля", reply=False)
        return

    session = Session()
    chat = get_chat(session, message.chat.id)
    chat.default_time = int(arg[1])
    session.commit()
    session.close()

    await message.reply(f"Таймер установлен на {int(arg[1])} минут", reply=False)

# /create [title]
@dp.message_handler(commands=["create"])
async def create_handler(message: Message):
    title = message.text[8:]
    if title.replace(" ", "") == "":
        await message.reply("Пустой заголовок. Испольузйте /create [text]\n",
                            reply=False)
        return
    if len(title) >= 3500:
        await message.reply("Заголовок не может быть длиннее 3500 символов",
                            reply=False)
        return
    session = Session()
    time = datetime.now()
    chat = get_chat(session, message.chat.id)
    delta = timedelta(minutes=chat.default_time)
    time += delta
    seconds = timedelta(time.second)
    time -= seconds

    message_bot = await message.reply(f"{title}\n\nВремя публикации: {time.strftime('%H:%M, %d.%m.%Y')}",
                                      reply=False)

    queue = Queue(creator_id=message.from_user.id, message_id=message_bot.message_id,
                  pin_date=time, title=title, chat_id=message.chat.id)
    session.add(queue)
    session.commit()
    session.close()

# /delete
@dp.message_handler(lambda msg: msg.reply_to_message is not None, commands=["delete"])
async def delete_handler(message: Message):
    session = Session()
    queue = session.query(Queue).filter(Queue.chat_id == message.chat.id,
                                        Queue.message_id == message.reply_to_message.message_id).first()
    if queue is None:
        session.close()
        return
    if queue.creator_id != message.from_user.id:
        await message.reply("Право закрыть очередь есть только у создателя")
        session.close()
        return
    else:
        if queue.is_pinned is False:
            await message.reply(f"{queue.title} удалена. Публикация по установленному времени отменена", reply=False)
            session.delete(queue)
            session.commit()
            session.close()
        else:
            await message.reply(f"{queue.title} закрыта. Сообщение и очередь удалены", reply=False)
            await bot.delete_message(queue.chat_id, queue.message_id)
            session.query(QueueRecord).filter(QueueRecord.queue_id == queue.id).delete()
            session.delete(queue)
            session.commit()
            session.close()

# reply @username on queue message
@dp.message_handler(lambda msg: is_reply_queue(msg))
async def queue_reply_handler(message: Message):
    username = message.text
    if "@" not in username or len(username) >= 3500:
        await message.reply("Неправильный `@юзернейм` или слишком длинное сообщение")
        return
    username_plain = username.replace("@", "")
    session = Session()
    __ = get_user(session, message.from_user)  # update sender obj
    user = session.query(User).filter(User.username == username_plain).first()
    if not user:
        session.close()
        await message.reply(f"`{username}` не найден.", parse_mode="Markdown")
        return
    queue = session.query(Queue).filter(Queue.message_id == message.reply_to_message.message_id).one()
    record = session.query(QueueRecord).filter(QueueRecord.user_id == user.id, QueueRecord.queue_id == queue.id).first()
    if record:
        session.close()
        await message.reply(f"`{username}` уже записан.", parse_mode="Markdown")
        return
    if len(session.query(QueueRecord).filter(QueueRecord.creator_id == message.from_user.id).all()) >= 1:
        session.close()
        await message.reply("Нельзя добавить больше 1 человека")
        return
    position = len(session.query(QueueRecord).filter(QueueRecord.queue_id == queue.id).all()) + 1
    session.add(QueueRecord(queue_id=queue.id, creator_id=message.from_user.id, user_id=user.id, position=position))
    session.commit()

    text = f"{queue.title}\n\nОчередь:"
    for record in session.query(QueueRecord).filter(QueueRecord.queue_id == queue.id).all():
        text += f"\n{record.position}. {record.user.user_name}"

    await bot.edit_message_text(text, queue.chat_id, queue.message_id, reply_markup=get_keyboard(queue))

    session.commit()
    session.close()

    await message.reply("Записано")

# [ Записаться ]
@dp.callback_query_handler(lambda callback: "add" in callback.data)
async def callback_add_handler(callback: CallbackQuery):
    queue_id = int(callback.data.split("-")[1])
    session = Session()
    record = session.query(QueueRecord).filter(QueueRecord.queue_id == queue_id,
                                               QueueRecord.user_id == callback.from_user.id).first()
    if record:
        session.close()
        await bot.answer_callback_query(callback.id, "Вы уже записаны")
        return

    queue = session.query(Queue).filter(Queue.id == queue_id).first()
    position = len(session.query(QueueRecord).filter(QueueRecord.queue_id == queue_id).all()) + 1
    user = get_user(session, callback.from_user)
    session.add(QueueRecord(queue_id=queue_id, user_id=callback.from_user.id, position=position))
    session.commit()

    text = f"{queue.title}\n\nОчередь:"
    for record in session.query(QueueRecord).filter(QueueRecord.queue_id == queue_id).all():
        text += f"\n{record.position}. {record.user.user_name}"

    await bot.answer_callback_query(callback.id, "Записано")
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
        await bot.answer_callback_query(callback.id, "Вы не записаны")
        return

    user = get_user(session, callback.from_user)
    queue = session.query(Queue).filter(Queue.id == queue_id).first()
    record.remove_record()
    session.commit()

    text = f"{queue.title}\n\nОчередь:"
    for record in session.query(QueueRecord).filter(QueueRecord.queue_id == queue_id).all():
        text += f"\n{record.position}. {record.user.user_name}"

    await bot.answer_callback_query(callback.id, "Выписано")
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
                                             f"{queue.title}\n\nОчередь:", reply_markup=get_keyboard(queue))
            try:
                if chat.pin:
                    await bot.pin_chat_message(queue.chat_id, message.message_id)
            except Exception as e:
                await bot.send_message(queue.chat_id, "Недостаточно прав для пина")

            queue.is_pinned = True
            queue.message_id = message.message_id
            session.commit()
        except Exception as e:
            print(e)


if __name__ == '__main__':
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_queue, "interval", seconds=5, max_instances=1, coalesce=True)
    scheduler.start()

    executor.start_polling(dp, skip_updates=True)
