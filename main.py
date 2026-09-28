import threading
import time
import feedparser
import requests
import telebot
import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set your token as an environment variable, or replace "YOUR_TOKEN_HERE" for testing
TELEGRAM_BOT_TOKEN = os.getenv("BOTTOKEN")
TELEGRAM_CHAT_ID = None
SUBS_FILE = "tracked_subs.json"

def load_subs():
    if os.path.exists(SUBS_FILE):
        try:
            with open(SUBS_FILE, "r") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"Error loading subs from file: {e}")
    return {"hardwareswap"}  # Default fallback

def save_subs():
    with open(SUBS_FILE, "w") as f:
        json.dump(list(TRACKED_SUBS), f)

# State variables
TRACKED_SUBS = load_subs() 
initialized_subs = set()
seen_posts = set()
bot_start_time = time.time()

# Updated User-Agent to prevent Reddit HTTP 429/403 blocks
HEADERS = {"User-Agent": "python:telegram-reddit-monitor:v1.0 (by /u/your_username)"}

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)


@bot.message_handler(commands=["status"])
def send_status(message):
    global TELEGRAM_CHAT_ID
    TELEGRAM_CHAT_ID = message.chat.id
    print(f"Captured working Chat ID: {TELEGRAM_CHAT_ID}")

    uptime_seconds = int(time.time() - bot_start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    subs_list = ", ".join([f"r/{sub}" for sub in TRACKED_SUBS]) if TRACKED_SUBS else "None"

    status_text = (
        f"🟢 *Bot Status: ONLINE*\n\n"
        f"⏱️ *Uptime:* {hours}h {minutes}m {seconds}s\n"
        f"📌 *Tracked Posts:* {len(seen_posts)}\n"
        f"📁 *Tracked Subs:* {subs_list}\n"
    )
    bot.reply_to(message, status_text, parse_mode="Markdown")


@bot.message_handler(commands=["addsub"])
def add_subreddit(message):
    global TELEGRAM_CHAT_ID
    TELEGRAM_CHAT_ID = message.chat.id

    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ *Usage:* `/addsub r/subname` or `/addsub subname`", parse_mode="Markdown")
        return
    
    new_sub = parts[1].strip().lower()
    if new_sub.startswith("r/"):
        new_sub = new_sub[2:]
    elif new_sub.startswith("/r/"):
        new_sub = new_sub[3:]
        
    if new_sub in TRACKED_SUBS:
        bot.reply_to(message, f"ℹ️ Already tracking *r/{new_sub}*", parse_mode="Markdown")
    else:
        TRACKED_SUBS.add(new_sub)
        save_subs()
        bot.reply_to(message, f"✅ Successfully added! Now tracking *r/{new_sub}*.\n\n_Note: I am fetching current posts silently so I don't spam you. You will only get alerts for brand new posts._", parse_mode="Markdown")


@bot.message_handler(commands=["removesub"])
def remove_subreddit(message):
    global TELEGRAM_CHAT_ID
    TELEGRAM_CHAT_ID = message.chat.id

    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ *Usage:* `/removesub r/subname` or `/removesub subname`", parse_mode="Markdown")
        return
    
    sub_to_remove = parts[1].strip().lower()
    if sub_to_remove.startswith("r/"):
        sub_to_remove = sub_to_remove[2:]
    elif sub_to_remove.startswith("/r/"):
        sub_to_remove = sub_to_remove[3:]
        
    if sub_to_remove in TRACKED_SUBS:
        TRACKED_SUBS.remove(sub_to_remove)
        save_subs()
        if sub_to_remove in initialized_subs:
            initialized_subs.remove(sub_to_remove)
        bot.reply_to(message, f"✅ Successfully removed! No longer tracking *r/{sub_to_remove}*.", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"ℹ️ You are not currently tracking *r/{sub_to_remove}*.", parse_mode="Markdown")


def send_telegram_alert(sub, title, link):
    if not TELEGRAM_CHAT_ID:
        return

    text = f"🚨 New on r/{sub}\n\n📌 {title}\n🔗 {link}"
    try:
        bot.send_message(
            TELEGRAM_CHAT_ID,
            text,
            disable_web_page_preview=False,
            timeout=45
        )
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")


def monitor_reddit_feed():
    print("Started Reddit RSS monitor...")
    
    while True:
        if not TRACKED_SUBS:
            time.sleep(10)
            continue
            
        for sub in list(TRACKED_SUBS):
            url = f"https://www.reddit.com/r/{sub}/new.rss"
            try:
                response = requests.get(url, headers=HEADERS, timeout=10)
                if response.status_code == 200:
                    feed = feedparser.parse(response.content)
                    
                    is_first_run = sub not in initialized_subs
                    
                    for entry in reversed(feed.entries):
                        post_id = entry.id
                        if post_id not in seen_posts:
                            seen_posts.add(post_id)
                            if not is_first_run:
                                title_lower = entry.title.lower()
                                
                                should_alert = False
                                
                                if sub == "hardwareswap":
                                    if "[h]" in title_lower and "[w]" in title_lower:
                                        h_index = title_lower.find("[h]")
                                        w_index = title_lower.find("[w]")
                                        h_section = title_lower[h_index:w_index]
                                        
                                        if not ("paypal" in h_section or "cash" in h_section):
                                            should_alert = True
                                else:
                                    should_alert = True 
                                    
                                if should_alert:
                                    send_telegram_alert(sub, entry.title, entry.link)

                    if is_first_run:
                        initialized_subs.add(sub)
                        print(f"Initialized r/{sub}, caught up on {len(feed.entries)} posts silently.")
                        
                else:
                    print(f"Failed to fetch r/{sub}. HTTP Status: {response.status_code}")
                    
            except Exception as e:
                print(f"Error checking feed for r/{sub}: {e}")

            time.sleep(2) 

        time.sleep(60)


if __name__ == "__main__":
    if TELEGRAM_BOT_TOKEN == "YOUR_TOKEN_HERE" or not TELEGRAM_BOT_TOKEN:
        print("WARNING: Please set your Telegram Bot Token.")
    else:
        # Start the RSS monitor in a background daemon thread
        monitor_thread = threading.Thread(target=monitor_reddit_feed, daemon=True)
        monitor_thread.start()

        # Create the command menu button in the Telegram UI
        try:
            bot.set_my_commands([
                telebot.types.BotCommand("/status", "Check bot status and uptime"),
                telebot.types.BotCommand("/addsub", "Add a subreddit"),
                telebot.types.BotCommand("/removesub", "Remove a subreddit")
            ])
        except Exception as e:
            print(f"Failed to set bot commands: {e}")

        print("Bot is listening for commands...")
        
        # Resilient polling loop catching connection errors (Flask removed)
        while True:
            try:
                bot.infinity_polling(interval=1, timeout=20, long_polling_timeout=20)
            except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout, ConnectionResetError) as e:
                print(f"\n[Network Notice] Connection dropped or timed out: {e}")
                print("Reconnecting to Telegram in 5 seconds...")
                time.sleep(5)
            except Exception as e:
                print(f"\n[Error] An unexpected polling error occurred: {e}")
                time.sleep(5)