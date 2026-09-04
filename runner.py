import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from pyrogram import filters
from pyrogram.handlers import MessageHandler, ChatMemberUpdatedHandler

import app as bot_app


# Pyrogram creates its Dispatcher and asyncio primitives when Client() is
# constructed. In app.py that happens during module import, while Uvicorn's
# real event loop is created later. Pyrogram 2.x stores the loop inside the
# Dispatcher, so merely changing Client.loop is not enough.
#
# This launcher repairs BOTH the Client and Dispatcher loop references before
# the existing FastAPI lifespan starts the bot. It also re-registers handlers
# on the live dispatcher because the decorators in app.py registered them on
# the import-time dispatcher loop.
@asynccontextmanager
async def fixed_lifespan(application):
    loop = asyncio.get_running_loop()

    bot = bot_app.bot
    bot.loop = loop
    bot.dispatcher.loop = loop
    bot.dispatcher.updates_queue = asyncio.Queue()
    bot.dispatcher.handler_worker_tasks.clear()
    bot.dispatcher.locks_list.clear()

    print(f"🔧 Runtime loop repaired: {id(loop)}")

    async with bot_app.lifespan(application):
        # The original lifespan resolves STORAGE_CHANNEL before yielding.
        # Register handlers only after that startup work is complete, using
        # the same live dispatcher/event loop.
        bot.add_handler(
            MessageHandler(
                bot_app.start_command,
                filters.command("start") & filters.private,
            ),
            group=0,
        )
        bot.add_handler(
            MessageHandler(
                bot_app.file_handler,
                filters.private & (filters.document | filters.video | filters.audio),
            ),
            group=1,
        )
        bot.add_handler(
            ChatMemberUpdatedHandler(
                bot_app.simple_gatekeeper,
                filters.chat(bot_app.Config.STORAGE_CHANNEL),
            ),
            group=0,
        )
        print("✅ Telegram message handlers registered on the live event loop.")
        yield


bot_app.app.router.lifespan_context = fixed_lifespan


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(bot_app.app, host="0.0.0.0", port=port, log_level="info")
