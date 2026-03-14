import asyncio
import logging
import os
import sys
import subprocess
import shutil

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from aiohttp import web

# Environment o'zgaruvchilarini olish
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEZER_ARL = os.getenv("DEEZER_ARL")

# Loglarni sozlash
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    logger.error("BOT_TOKEN o'rnatilmagan! Iltimos parametrni Render dagi muhit o'zgaruvchilariga (environment variables) qo'shing.")
    sys.exit(1)

if not DEEZER_ARL:
    logger.warning("DEEZER_ARL topilmadi! Bu xato berishi mumkin. Iltimos ARL kodni qo'shing.")

# ARL faylini yaratish (Deemix portable ishlashi uchun)
ARL_PATH = os.path.join(os.getcwd(), '.arl')
if DEEZER_ARL:
    with open(ARL_PATH, "w") as f:
        f.write(DEEZER_ARL.strip())

# Bot va Dispatcher yaratish
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- Dummy Web Server ---
# Render.com bepul Web Service larini o'chirmasligi uchun PORT ga quloq soluvchi kichik server
async def handle_ping(request):
    return web.Response(text="Bot ishlamoqda!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/ping', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Yolg'onchi (Dummy) web server {port} portida ishga tushdi")

# --- Bot Handler'lari ---
@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    await message.answer("Salom! Men Deezer musiqalarini (FLAC sifatda) yuklab beruvchi botman.\n\nMenga Deezer musiqasining havolasini yuboring (masalan: <i>https://deezer.page.link/...</i>).")

@dp.message(Command("help"))
async def command_help_handler(message: types.Message) -> None:
    await message.answer("Deezer ilovasidan musiqaning ulashish havolasini (share link) nusxalab menga yuboring. Men uni yuklashga harakat qilaman.")

@dp.message()
async def download_deezer_link(message: types.Message) -> None:
    url = message.text
    if "deezer" not in url.lower():
        await message.reply("Iltimos, faqat Deezer havolasini yuboring.")
        return

    status_msg = await message.reply("⏳ <i>Musiqa qidirilmoqda... Bu biroz vaqt olishi mumkin.</i>")

    # Yuklab olinadigan joy qavati
    download_dir = os.path.join(os.getcwd(), f"downloads_{message.from_user.id}_{message.message_id}")
    os.makedirs(download_dir, exist_ok=True)

    try:
        def run_deemix():
            # deemix ni python CLI moduli orqali ishga tushirish: python -m deemix --portable -p <dir> -b FLAC <url>
            command = [
                sys.executable, "-m", "deemix", 
                "--portable", 
                "-p", download_dir, 
                "-b", "FLAC", 
                url
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            return result.returncode, result.stdout, result.stderr

        await status_msg.edit_text("⏳ <i>Deemix orqali yuklab olinmoqda (FLAC)...</i>")
        code, stdout, stderr = await asyncio.to_thread(run_deemix)
        
        # Jild ichidan yuklangan faylni qidiramiz
        downloaded_file = None
        for root, _, files in os.walk(download_dir):
            for file in files:
                if file.endswith((".flac", ".mp3")):
                    downloaded_file = os.path.join(root, file)
                    break
            if downloaded_file:
                break

        if downloaded_file is not None and os.path.exists(downloaded_file):
            await status_msg.edit_text("✅ <i>Yuklandi! Telegram serveriga yuborilmoqda...</i>")
            
            # Audio faylni yuborish
            audio = FSInputFile(downloaded_file)
            await bot.send_audio(
                chat_id=message.chat.id,
                audio=audio,
                caption="🎵 Deezer'dan yuklandi.\n@SizningBotingizYoziladi", # O'zingizning botingiz nomini yozing
                reply_to_message_id=message.message_id
            )
            await status_msg.delete()
        else:
            logger.error(f"Fayl topilmadi. Deemix output: {stdout}\nErrors: {stderr}")
            error_text = "❌ <b>Xatolik:</b> Fayl yuklanmadi. Bunga ARL kodi eskirganligi (yo'qligi) yoki havola xato ekani sabab bo'lishi mumkin."
            await status_msg.edit_text(error_text)

    except Exception as e:
        logger.error(f"Yuklashda xatolik {url}: {e}")
        error_text = f"❌ <b>Xatolik yuz berdi:</b> {str(e)}"
        await status_msg.edit_text(error_text)
    
    finally:
        # Yakunda qoldiq papkani xotiradan tozalab tashlash
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir, ignore_errors=True)


async def main():
    logger.info("Bot ishga tushirildi...")
    
    # Kichik web serverni ishga tushirish (Render uchun)
    asyncio.create_task(web_server())
    
    # Telegram bot polling'ni ishga tushirish
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi!")
