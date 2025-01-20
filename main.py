import os
import sqlite3
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import asyncio

# Telegram bot setup
TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
bot_app = Application.builder().token(TOKEN).build()

# Database setup
DB_PATH = "votes.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

# Create necessary tables
cursor.executescript("""
CREATE TABLE IF NOT EXISTS votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    name TEXT,
    vote_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS channels (
    user_id INTEGER PRIMARY KEY,
    channel_id INTEGER,
    channel_username TEXT
);
CREATE TABLE IF NOT EXISTS banners (
    user_id INTEGER PRIMARY KEY,
    banner BLOB
);
CREATE TABLE IF NOT EXISTS voters (
    user_id INTEGER,
    username TEXT,
    PRIMARY KEY (user_id, username)
);
""")
conn.commit()

# Handler for the /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command with automatic /votep execution for participants."""
    user = update.effective_user

    if context.args:
        try:
            channel_id = int(context.args[0])

            # Verify if the user is a member of the channel
            try:
                chat_member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user.id)
                if chat_member.status not in ["member", "administrator", "creator"]:
                    raise ValueError("Not a member")
            except Exception:
                # Fetch channel username
                cursor.execute("SELECT channel_username FROM channels WHERE channel_id = ?", (channel_id,))
                channel = cursor.fetchone()
                channel_username = channel[0] if channel else "Unknown"
                await update.message.reply_text(
                    f"You need to join @{channel_username} to participate. Please join the channel and try again."
                )
                return

            # Automatically detect username and name
            username = user.username or f"user_{user.id}"
            name = user.full_name or "Anonymous"

            # Check if the banner is set
            cursor.execute("SELECT banner FROM banners WHERE user_id = ?", (user.id,))
            banner = cursor.fetchone()
            if not banner:
                await update.message.reply_text("Please set a banner using /setbanner first.")
                return

            banner_data = BytesIO(banner[0])

            # Save participant to the database
            cursor.execute("INSERT OR IGNORE INTO votes (user_id, username, name, vote_count) VALUES (?, ?, ?, ?)",
                           (user.id, username, name, 0))
            conn.commit()

            # Inline button for voting
            keyboard = [[InlineKeyboardButton(f"🔥 Vote (0)", callback_data=f"vote_{username}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send participant info and voting button to the channel
            await context.bot.send_photo(
                chat_id=channel_id,
                photo=banner_data,
                caption=f"**PARTICIPANT INFORMATION**\n\n"
                        f"‣ Name: {name}\n"
                        f"‣ Username: @{username}\n\n"
                        "📌 **Note**: Only members of this channel can vote!\n\n"
                        "✨ Thank you for participating in the voting event.",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )

            # Confirm participation in private chat
            await update.message.reply_text(
                f"🎉 Welcome to the voting event!\n\n"
                f"You have been successfully registered as a participant in the channel."
            )
        except ValueError:
            await update.message.reply_text("Invalid channel ID. Please try again.")
    else:
        await update.message.reply_text("Welcome! Use /help to see available commands.")


# /help Command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command."""
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Start the bot\n"
        "/setchannel - Configure your channel\n"
        "/votep - Register a participant\n"
        "/votepL - Generate a participation link\n"
        "/setbanner - Set your banner\n"
        "/V - Update votes manually"
    )


# /setbanner Command
async def setbanner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set a custom banner for votes."""
    user = update.effective_user

    if len(context.args) != 1 or context.args[0] != "872@RrR":
        await update.message.reply_text("Unauthorized: Incorrect password.")
        return

    await update.message.reply_text("Please send the banner image.")

    def check(update: Update):
        return bool(update.message.photo)

    try:
        update_with_photo = await bot_app.wait_for_message(filters.PHOTO & filters.user(user.id), timeout=60)
        if update_with_photo:
            file = await update_with_photo.message.photo[-1].get_file()
            image_binary = await file.download_as_bytearray()

            cursor.execute("INSERT OR REPLACE INTO banners (user_id, banner) VALUES (?, ?)", (user.id, image_binary))
            conn.commit()
            await update.message.reply_text("Banner has been set successfully!")
    except asyncio.TimeoutError:
        await update.message.reply_text("No image received. Please try again.")


# /setchannel Command
async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set the channel for a user."""
    if len(context.args) != 3:
        await update.message.reply_text("Usage: /setchannel <user_id> <channel_id> <channel_username>")
        return

    user_id, channel_id, channel_username = context.args
    cursor.execute("INSERT OR REPLACE INTO channels (user_id, channel_id, channel_username) VALUES (?, ?, ?)",
                   (user_id, channel_id, channel_username))
    conn.commit()
    await update.message.reply_text(f"Channel set for user {user_id}.")


# /votep Command
async def votep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register a participant with a voting inline button."""
    user = update.effective_user
    cursor.execute("SELECT banner FROM banners WHERE user_id = ?", (user.id,))
    banner = cursor.fetchone()
    if not banner:
        await update.message.reply_text("Please set a banner using /setbanner first.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /votep <username> <name>")
        return

    username = context.args[0]
    name = " ".join(context.args[1:])
    cursor.execute("SELECT channel_id FROM channels WHERE user_id = ?", (user.id,))
    channel = cursor.fetchone()
    if not channel:
        await update.message.reply_text("Please set a channel using /setchannel first.")
        return

    channel_id = channel[0]
    banner_data = BytesIO(banner[0])
    cursor.execute("INSERT OR IGNORE INTO votes (user_id, username, name, vote_count) VALUES (?, ?, ?, ?)",
                   (user.id, username, name, 0))
    conn.commit()

    keyboard = [[InlineKeyboardButton(f"🔥 Vote (0)", callback_data=f"vote_{username}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_photo(
            chat_id=channel_id,
            photo=banner_data,
            caption=f"**PARTICIPANT INFORMATION**\n\n"
                    f"‣ Name: {name}\n"
                    f"‣ Username: @{username}\n\n"
                    "📌 **Note**: Only members of this channel can vote!\n\n"
                    "✨ Thank you for participating in the voting event.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        await update.message.reply_text(f"Participant {name} has been registered and added to the channel.")
    except Exception as e:
        await update.message.reply_text(f"Error sending participant details: {e}")


# Vote Button Callback
async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle vote button clicks."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("vote_"):
        return

    username = data.split("_", 1)[1]
    voter_id = query.from_user.id
    cursor.execute("SELECT channel_id FROM channels WHERE user_id = (SELECT user_id FROM votes WHERE username = ?)", (username,))
    channel = cursor.fetchone()

    if not channel:
        await query.message.reply_text("Channel information not found. Please contact the admin.")
        return

    channel_id = channel[0]

    try:
        chat_member = await context.bot.get_chat_member(chat_id=channel_id, user_id=voter_id)
        if chat_member.status not in ["member", "administrator", "creator"]:
            raise Exception("Not a member")
    except Exception:
        await query.message.reply_text("You must join the channel to vote.")
        return

    cursor.execute("INSERT OR IGNORE INTO voters (user_id, username) VALUES (?, ?)", (voter_id, username))
    cursor.execute("UPDATE votes SET vote_count = vote_count + 1 WHERE username = ?", (username,))
    conn.commit()

    cursor.execute("SELECT vote_count FROM votes WHERE username = ?", (username,))
    vote_count = cursor.fetchone()[0]
    keyboard = [[InlineKeyboardButton(f"🔥 Vote ({vote_count})", callback_data=f"vote_{username}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.message.edit_reply_markup(reply_markup=reply_markup)
    except Exception as e:
        print(f"Error updating vote count: {e}")
        await query.message.reply_text(f"Error updating vote count: {e}")


# Periodic Check to Uncount Votes for Leavers
async def uncount_leavers():
    """Deduct votes from users who left the channel."""
    while True:
        cursor.execute("SELECT username, channel_id, user_id FROM voters")
        voters = cursor.fetchall()

        for username, channel_id, voter_id in voters:
            try:
                chat_member = await bot_app.bot.get_chat_member(chat_id=channel_id, user_id=voter_id)
                if chat_member.status not in ["member", "administrator", "creator"]:
                    cursor.execute("UPDATE votes SET vote_count = vote_count - 1 WHERE username = ?", (username,))
                    cursor.execute("DELETE FROM voters WHERE user_id = ? AND username = ?", (voter_id, username))
                    conn.commit()
            except Exception as e:
                print(f"Error checking user {voter_id} in channel {channel_id}: {e}")

        await asyncio.sleep(300)  # Check every 5 minutes


# /votepL Command
async def votepL(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a participation link for a user."""
    user = update.effective_user
    cursor.execute("SELECT channel_id, channel_username FROM channels WHERE user_id = ?", (user.id,))
    channel = cursor.fetchone()
    if not channel:
        await update.message.reply_text("Please set a channel using /setchannel first.")
        return

    channel_id, channel_username = channel
    participation_link = f"https://t.me/{context.bot.username}?start={channel_id}"

    await update.message.reply_text(
        f"Share this participation link:\n\n{participation_link}\n\n"
        f"📌 Users must join the channel @{channel_username} to participate. "
        "If they leave, their participation will be invalidated."
    )


# Register Handlers
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("help", help_command))
bot_app.add_handler(CommandHandler("setbanner", setbanner))
bot_app.add_handler(CommandHandler("setchannel", set_channel))
bot_app.add_handler(CommandHandler("votep", votep))
bot_app.add_handler(CallbackQueryHandler(vote_callback))
bot_app.add_handler(CommandHandler("votepL", votepL))

# Run the bot
if __name__ == "__main__":
    asyncio.run(bot_app.start())
    asyncio.create_task(uncount_leavers())
