from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext
from datetime import datetime, timedelta
from tinydb import TinyDB, Query
import pytz

# Initialize TinyDB
db = TinyDB('pomodoro_log.json')
user_db = Query()

# Telegram bot token
BOT_TOKEN = '7796568844:AAHKvvTLKdrsRb29izWEY8wi2w1iMBdXmiY'

# Dictionary to track current users and session state
user_identification = {}
user_sessions = {}

# Timezone for accurate leaderboard and summaries
TIMEZONE = pytz.timezone('Asia/Singapore')

# Helper function to get the start of the day in the correct timezone
def start_of_day(dt):
    return dt.astimezone(TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)

# Helper function to get the start of the week
def start_of_week(dt):
    return start_of_day(dt) - timedelta(days=dt.weekday())

# Start message with user selection buttons
async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("Benjamin", callback_data='setuser_Benjamin')],
        [InlineKeyboardButton("Ziyu", callback_data='setuser_Ziyu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome! Please select your user:", reply_markup=reply_markup)
    await show_menu(update, context)

# Create a main menu keyboard with all the features
async def show_menu(update: Update, context: CallbackContext) -> None:
    menu_keyboard = [
        [KeyboardButton("/start"), KeyboardButton("/leaderboard")],
        [KeyboardButton("/pause"), KeyboardButton("/resume")],
        [KeyboardButton("/showtime"), KeyboardButton("/leave")],
        [KeyboardButton("/stats"), KeyboardButton("/reset")],
    ]
    menu_markup = ReplyKeyboardMarkup(menu_keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("Main Menu", reply_markup=menu_markup)

# Handle user selection and show Pomodoro options
async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("setuser_"):
        user_name = data.split("_")[1]
        chat_id = query.message.chat_id
        user_identification[chat_id] = user_name

        await query.edit_message_text(f"User set to {user_name}. Please enter the purpose of this session:")
        context.user_data['awaiting_purpose'] = True

    elif data.startswith("startpomodoro_"):
        _, user_name, duration = data.split("_")
        chat_id = query.message.chat_id
        duration = int(duration)

        if chat_id in user_sessions and user_sessions[chat_id]['status'] == 'active':
            await query.edit_message_text(f"You already have an active Pomodoro session. Use /leave or /pause to manage it.")
            return

        end_time = datetime.now() + timedelta(minutes=duration)
        user_sessions[chat_id] = {
            'user_name': user_name,
            'start_time': datetime.now(),
            'end_time': end_time,
            'remaining_time': duration * 60,
            'status': 'active',
            'purpose': context.user_data.get('purpose', 'No purpose specified')
        }
        context.job_queue.run_once(end_pomodoro, duration * 60, data={'chat_id': chat_id, 'user_name': user_name})

        await query.edit_message_text(f"Pomodoro started for {duration} minutes as {user_name}!\nPurpose: {user_sessions[chat_id]['purpose']}")
        db.insert({
            'user': user_name,
            'chat_id': chat_id,
            'start': str(datetime.now()),
            'end': str(end_time),
            'purpose': user_sessions[chat_id]['purpose'],
            'status': 'active'
        })

    elif data == "custom_pomodoro":
        chat_id = query.message.chat_id
        user_name = user_identification.get(chat_id, 'Unknown')
        await query.edit_message_text(f"Please enter the custom Pomodoro duration in minutes for {user_name}:")
        context.user_data['awaiting_custom_duration'] = True

# Modified `custom_pomodoro` to accept input duration
async def custom_pomodoro(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    if chat_id not in user_identification:
        await update.message.reply_text("Please set your user first using /start.")
        return

    user_name = user_identification[chat_id]
    try:
        duration = int(update.message.text)  # Get the duration from user message
        if duration <= 0:
            await update.message.reply_text("Please provide a positive duration in minutes.")
            return
        end_time = datetime.now() + timedelta(minutes=duration)
        user_sessions[chat_id] = {
            'user_name': user_name,
            'start_time': datetime.now(),
            'end_time': end_time,
            'remaining_time': duration * 60,
            'status': 'active',
            'purpose': context.user_data.get('purpose', 'Custom Pomodoro')
        }
        context.job_queue.run_once(end_pomodoro, duration * 60, data={'chat_id': chat_id, 'user_name': user_name})
        await update.message.reply_text(f"Custom Pomodoro started for {duration} minutes as {user_name}!")
        db.insert({
            'user': user_name,
            'chat_id': chat_id,
            'start': str(datetime.now()),
            'end': str(end_time),
            'purpose': context.user_data.get('purpose', 'Custom Pomodoro'),
            'status': 'active'
        })
    except (IndexError, ValueError):
        await update.message.reply_text("Please provide a valid duration in minutes.")

# Log the purpose when the user provides it
async def purpose_input(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id

    if 'awaiting_purpose' in context.user_data and context.user_data['awaiting_purpose']:
        context.user_data['purpose'] = update.message.text
        context.user_data['awaiting_purpose'] = False

        # Show Pomodoro timer options after receiving the purpose
        user_name = user_identification[chat_id]
        keyboard = [
            [InlineKeyboardButton("25 min", callback_data=f'startpomodoro_{user_name}_25')],
            [InlineKeyboardButton("45 min", callback_data=f'startpomodoro_{user_name}_45')],
            [InlineKeyboardButton("1 hour", callback_data=f'startpomodoro_{user_name}_60')],
            [InlineKeyboardButton("Custom Duration", callback_data='custom_pomodoro')]  # Add custom duration option
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Purpose noted. Choose your Pomodoro timer:", reply_markup=reply_markup)

    elif 'awaiting_custom_duration' in context.user_data and context.user_data['awaiting_custom_duration']:
        await custom_pomodoro(update, context)
        context.user_data['awaiting_custom_duration'] = False
    else:
        await update.message.reply_text("Please select your user first using /start.")

# End the Pomodoro session
async def end_pomodoro(context: CallbackContext) -> None:
    job = context.job
    chat_id = job.data['chat_id']
    user_name = job.data['user_name']

    session = user_sessions.get(chat_id, {})
    if session and session['status'] in ['paused', 'ended_early']:
        await context.bot.send_message(chat_id, text=f"Pomodoro session for {user_name} was ended early.")
    else:
        await context.bot.send_message(chat_id, text=f"Pomodoro session ended! Take a break, {user_name}.")
        
        # Update the session as completed in the database with actual end time
        db.update({'status': 'completed', 'end': str(datetime.now())}, (user_db.chat_id == chat_id) & (user_db.status == 'active'))
        user_sessions.pop(chat_id, None)

# Pause the current Pomodoro session
async def pause(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    session = user_sessions.get(chat_id, {})
    if session and session['status'] == 'active':
        remaining_time = (session['end_time'] - datetime.now()).seconds
        session['remaining_time'] = remaining_time
        session['status'] = 'paused'
        context.job_queue.jobs()[0].schedule_removal()  # Remove scheduled job
        await update.message.reply_text(f"Pomodoro paused with {remaining_time // 60} minutes left.")
    else:
        await update.message.reply_text("No active Pomodoro session to pause.")

# Resume the paused Pomodoro session
async def resume(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    session = user_sessions.get(chat_id, {})
    if session and session['status'] == 'paused':
        session['end_time'] = datetime.now() + timedelta(seconds=session['remaining_time'])
        session['status'] = 'active'
        context.job_queue.run_once(end_pomodoro, session['remaining_time'], data={'chat_id': chat_id, 'user_name': session['user_name']})
        await update.message.reply_text(f"Pomodoro resumed with {session['remaining_time'] // 60} minutes left.")
    else:
        await update.message.reply_text("No paused Pomodoro session to resume.")

# Show the remaining time of the current session
async def show_time(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    session = user_sessions.get(chat_id, {})
    if session:
        remaining_time = (session['end_time'] - datetime.now()).seconds if session['status'] == 'active' else session['remaining_time']
        await update.message.reply_text(f"Remaining time: {remaining_time // 60} minutes and {remaining_time % 60} seconds.")
    else:
        await update.message.reply_text("No active Pomodoro session.")

# Leave the Pomodoro session early
async def leave(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    session = user_sessions.get(chat_id, {})
    if session:
        elapsed_time = (datetime.now() - session['start_time']).seconds
        user_sessions.pop(chat_id, None)

        # Update the session as ended early in the database with actual time
        db.update({'status': 'ended_early', 'end': str(datetime.now())}, (user_db.chat_id == chat_id) & (user_db.status == 'active'))
        await update.message.reply_text(f"You have left the Pomodoro session early. Total time: {elapsed_time // 60} minutes.")
    else:
        await update.message.reply_text("No active Pomodoro session to leave.")

# Reset the database
async def reset(update: Update, context: CallbackContext) -> None:
    db.truncate()  # Clear the database
    await update.message.reply_text("All Pomodoro data has been reset.")

# Show statistics for each user
async def stats(update: Update, context: CallbackContext) -> None:
    today = datetime.now(TIMEZONE).date()
    total_time_benjamin = 0
    total_time_ziyu = 0
    
    # Calculate total Pomodoro minutes for each user, include both completed and ended_early sessions
    for record in db.search((user_db.status == 'completed') | (user_db.status == 'ended_early')):
        start_time = datetime.fromisoformat(record['start']).replace(tzinfo=TIMEZONE)
        if start_time.date() == today:
            end_time = datetime.fromisoformat(record['end']).replace(tzinfo=TIMEZONE)
            user = record['user']
            total_minutes = (end_time - start_time).seconds // 60
            
            if user == "Benjamin":
                total_time_benjamin += total_minutes
            elif user == "Ziyu":
                total_time_ziyu += total_minutes
    
    await update.message.reply_text(
        f"Total Pomodoro time today:\nBenjamin: {total_time_benjamin} minutes\nZiyu: {total_time_ziyu} minutes"
    )

# Show leaderboard for the current week
async def leaderboard(update: Update, context: CallbackContext) -> None:
    start_of_the_week = start_of_week(datetime.now(TIMEZONE))
    leaderboard_data = {"Benjamin": 0, "Ziyu": 0}

    for record in db.search((user_db.status == 'completed') | (user_db.status == 'ended_early')):
        start_time = datetime.fromisoformat(record['start']).replace(tzinfo=TIMEZONE)
        end_time = datetime.fromisoformat(record['end']).replace(tzinfo=TIMEZONE)
        
        if start_time >= start_of_the_week:
            user = record['user']
            total_minutes = (end_time - start_time).seconds // 60
            if user in leaderboard_data:
                leaderboard_data[user] += total_minutes

    await update.message.reply_text(
        f"Leaderboard (Current Week):\nBenjamin: {leaderboard_data['Benjamin']} minutes\nZiyu: {leaderboard_data['Ziyu']} minutes"
    )

def main() -> None:
    # Create application with the BOT_TOKEN
    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("custom_pomodoro", custom_pomodoro))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))
    application.add_handler(CommandHandler("showtime", show_time))
    application.add_handler(CommandHandler("leave", leave))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("menu", show_menu))  # Show the menu with available features

    # Callback query handler for button clicks
    application.add_handler(CallbackQueryHandler(button_handler))

    # Message handler for purpose input
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, purpose_input))

    # Run the bot
    application.run_polling()

if __name__ == '__main__':
    main()






# BOT_TOKEN = '7796568844:AAHKvvTLKdrsRb29izWEY8wi2w1iMBdXmiY'