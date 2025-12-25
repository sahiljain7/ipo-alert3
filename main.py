import requests
import sqlite3
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import os

BOT_TOKEN = os.environ["BOT_TOKEN"]
MIN_ISSUE_SIZE = 500  # Cr
NSE_API = "https://www.nseindia.com/api/ipo-current-issue"

# ---------------- DB ----------------
conn = sqlite3.connect("ipo.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS ipo_state (
    ipo_name TEXT PRIMARY KEY,
    open_sent INTEGER,
    last_day_sent INTEGER,
    interest TEXT
)
""")
conn.commit()

# ---------------- NSE ----------------
def get_ipos():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    })
    session.get("https://www.nseindia.com", timeout=10)
    time.sleep(1)
    return session.get(NSE_API, timeout=20).json()

def parse_size(size):
    try:
        return float(size.lower().replace("cr", "").replace(",", "").strip())
    except:
        return 0

# ---------------- BOT ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("IPO Alert Bot is active.")

async def handle_interest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ipo, choice = query.data.split("|")
    cur.execute(
        "UPDATE ipo_state SET interest=? WHERE ipo_name=?",
        (choice, ipo)
    )
    conn.commit()

    await query.edit_message_text(
        f"{ipo}\n\nInterest recorded: {choice.upper()}"
    )

async def daily_check(context: ContextTypes.DEFAULT_TYPE):
    ipos = get_ipos()
    today = datetime.today().strftime("%d-%b-%Y")

    for ipo in ipos:
        name = ipo.get("companyName")
        size = parse_size(ipo.get("issueSize", ""))
        if size < MIN_ISSUE_SIZE:
            continue

        start = ipo.get("issueStartDate")
        end = ipo.get("issueEndDate")
        status = ipo.get("status", "").lower()

        cur.execute("SELECT * FROM ipo_state WHERE ipo_name=?", (name,))
        row = cur.fetchone()

        if not row:
            cur.execute(
                "INSERT INTO ipo_state VALUES (?,0,0,'unknown')",
                (name,)
            )
            conn.commit()
            row = (name, 0, 0, "unknown")

        _, open_sent, last_sent, interest = row

        # OPEN ALERT
        if status == "open" and not open_sent:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes", callback_data=f"{name}|yes"),
                    InlineKeyboardButton("❌ No", callback_data=f"{name}|no")
                ]
            ])

            await context.bot.send_message(
                chat_id=context.job.chat_id,
                text=(
                    f"📢 IPO OPEN\n\n"
                    f"{name}\n"
                    f"Issue Size: ₹{size} Cr\n"
                    f"{start} → {end}\n\n"
                    f"Interested?"
                ),
                reply_markup=keyboard
            )

            cur.execute(
                "UPDATE ipo_state SET open_sent=1 WHERE ipo_name=?",
                (name,)
            )
            conn.commit()

        # LAST DAY ALERT
        if end == today and not last_sent and interest != "no":
            await context.bot.send_message(
                chat_id=context.job.chat_id,
                text=(
                    f"⏰ LAST DAY TO APPLY\n\n"
                    f"{name}\n"
                    f"Issue Size: ₹{size} Cr\n"
                )
            )
            cur.execute(
                "UPDATE ipo_state SET last_day_sent=1 WHERE ipo_name=?",
                (name,)
            )
            conn.commit()

# ---------------- RUN ----------------
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(handle_interest))

app.job_queue.run_repeating(
    daily_check,
    interval=86400,
    first=5,
    chat_id=os.environ["CHAT_ID"]
)

app.run_polling()
