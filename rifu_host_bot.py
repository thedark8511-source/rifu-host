#!/usr/bin/env python3
# RIFU BOT HOSTING v2 - py file hosting
# Render pe deploy karo. Jo bot chalana hai uska .py file isi
# bot ko bhejo (+ token), ye background me run karega.
# File me token aise lo: TOKEN = os.environ.get("BOT_TOKEN", "...")
# Needs: pip install python-telegram-bot aiohttp
# Run: BOT_TOKEN=main_token ADMIN_ID=tere_id python3 rifu_host_bot.py
import os, json, time, asyncio, logging, subprocess, shutil
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

TOKEN = os.environ.get("9035932988:AAHGxlyqbwXblFEkPuqk-5gr3VUf0V_BmMM")
ADMIN_ID = int(os.environ.get("7224288984", "0"))
DATA_FILE = "host_data.json"
BOT_DIR = "hosted_bots"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rifuhost")

DB = {"bots": {}}
def save():
    with open(DATA_FILE, "w") as f:
        json.dump(DB, f)
try:
    with open(DATA_FILE) as f:
        DB = json.load(f)
except Exception:
    pass
os.makedirs(BOT_DIR, exist_ok=True)

def is_admin(u): return ADMIN_ID and u.id == ADMIN_ID

PROCS = {}

def alive(bid):
    p = PROCS.get(bid)
    return bool(p and p.poll() is None)

def launch(bid):
    info = DB["bots"][bid]
    folder = os.path.join(BOT_DIR, bid)
    script = os.path.join(folder, info["name"])
    logfile = open(os.path.join(folder, "out.log"), "ab")
    env = dict(os.environ)
    env["BOT_TOKEN"] = info["token"]
    env["ADMIN_ID"] = str(info["owner"])
    p = subprocess.Popen(["python3", "-u", script], cwd=folder, stdout=logfile, stderr=logfile, env=env)
    PROCS[bid] = p
    info["running"] = True
    save()

def kill(bid):
    p = PROCS.pop(bid, None)
    if p and p.poll() is None:
        try: p.kill()
        except Exception: pass
    if bid in DB["bots"]:
        DB["bots"][bid]["running"] = False
        save()

async def watch():
    while True:
        await asyncio.sleep(10)
        for bid, info in list(DB["bots"].items()):
            if info.get("running") and not alive(bid):
                log.warning(f"bot {bid} died, restarting")
                try: launch(bid)
                except Exception as e:
                    log.warning(f"restart fail: {e}")

def bots_kb():
    rows = []
    for bid, info in DB["bots"].items():
        st = "ON" if alive(bid) else "OFF"
        rows.append([InlineKeyboardButton(f"{st} {info['name'][:20]}", callback_data=f"b:{bid}")])
    return InlineKeyboardMarkup(rows)

def bot_kb(bid):
    run = alive(bid)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Stop" if run else "Start", callback_data=f"m:{'stop' if run else 'start'}:{bid}")],
        [InlineKeyboardButton("Logs", callback_data=f"m:logs:{bid}"),
         InlineKeyboardButton("Delete", callback_data=f"m:del:{bid}")],
    ])

START_TXT = (
    "RIFU BOT HOSTING\n\n"
    "1. apne bot ka .py file bhejo\n"
    "2. fir uska bot token bhej (123456:ABC...)\n"
    "3. bot live chal jayega\n\n"
    "file me token aise lo: TOKEN = os.environ.get('BOT_TOKEN', '...')\n"
    "/admin = panel")

async def start(update, ctx):
    await update.message.reply_text(START_TXT)

async def admin(update, ctx):
    if not is_admin(update.effective_user):
        await update.message.reply_text("admin only"); return
    await update.message.reply_text("HOSTED BOTS", reply_markup=bots_kb())

async def on_doc(update: Update, ctx):
    if not is_admin(update.effective_user):
        await update.message.reply_text("admin only"); return
    doc = update.message.document
    if not doc or not doc.file_name.endswith(".py"):
        await update.message.reply_text("sirf .py file bhej bhai")
        return
    f = await doc.get_file()
    bid = str(int(time.time() * 1000))[-9:]
    folder = os.path.join(BOT_DIR, bid)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, doc.file_name)
    await f.download_to_drive(path)
    src = open(path, encoding="utf-8", errors="ignore").read()
    warn = ""
    if "BOT_TOKEN" not in src:
        warn = " (token hardcode hai toh bhi chalega, par BOT_TOKEN env better)"
    DB["bots"][bid] = {"name": doc.file_name, "owner": update.effective_user.id,
                       "token": "", "running": False, "added": int(time.time())}
    save()
    ctx.user_data["awaiting_token_for"] = bid
    await update.message.reply_text(f"{doc.file_name} mil gaya.{warn} ab iska bot token bhej, live kar dunga.")

async def on_text(update: Update, ctx):
    text = (update.message.text or "").strip()
    bid = ctx.user_data.get("awaiting_token_for")
    if bid and bid in DB["bots"] and ":" in text and text.split(":")[0].isdigit():
        token = text
        try: await update.message.delete()
        except Exception: pass
        me = None
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://api.telegram.org/bot{token}/getMe") as r:
                    me = (await r.json()).get("result")
        except Exception:
            pass
        if not me:
            await update.message.reply_text("token galat, BotFather ka sahi bhej")
            return
        DB["bots"][bid]["token"] = token
        save()
        ctx.user_data["awaiting_token_for"] = None
        launch(bid)
        await update.message.reply_text(f"@{me.get('username')} live ho gaya!", reply_markup=bot_kb(bid))
        return
    await update.message.reply_text(".py file bhej + token, ya /admin dekh le")

async def cb(update: Update, ctx):
    q = update.callback_query
    d = q.data
    if d.startswith("b:"):
        bid = d[2:]
        info = DB["bots"].get(bid)
        await q.answer()
        if info:
            st = "chalu" if alive(bid) else "band"
            await q.message.reply_text(f"{info['name']}\nstatus: {st}", reply_markup=bot_kb(bid))
        return
    _, act, bid = d.split(":", 2)
    info = DB["bots"].get(bid)
    if not info:
        await q.answer("not found", show_alert=True); return
    if act == "del":
        kill(bid); shutil.rmtree(os.path.join(BOT_DIR, bid), ignore_errors=True)
        DB["bots"].pop(bid); save()
        await q.answer(); await q.edit_message_text("deleted")
    elif act == "stop":
        kill(bid)
        await q.answer("stopped"); await q.edit_message_reply_markup(reply_markup=bot_kb(bid))
    elif act == "start":
        if not info["token"]:
            await q.answer("token nahi hai is bot ka", show_alert=True); return
        launch(bid)
        await q.answer("started"); await q.edit_message_reply_markup(reply_markup=bot_kb(bid))
    elif act == "logs":
        try:
            lf = os.path.join(BOT_DIR, bid, "out.log")
            tail = open(lf, "rb").read()[-1500:].decode("utf-8", "ignore")
        except Exception:
            tail = ""
        await q.answer()
        await q.message.reply_text("logs:\n" + (tail.strip() or "(koi log nahi)"))

async def on_boot(app):
    for bid, info in DB["bots"].items():
        if info.get("token"):
            try: launch(bid)
            except Exception as e:
                log.warning(f"boot fail {bid}: {e}")
    app.create_task(watch())

def main():
    app = Application.builder().token(TOKEN).post_init(on_boot).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(MessageHandler(filters.Document.ALL, on_doc))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info(f"RIFU HOSTING v2 started, {len(DB['bots'])} bots")
    app.run_polling()

if __name__ == "__main__":
    main()
