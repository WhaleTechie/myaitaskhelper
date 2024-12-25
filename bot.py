import os
import datetime
import openai
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, JobQueue
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Configurations
BOT_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'
OPENAI_API_KEY = 'YOUR_OPENAI_API_KEY'
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Set OpenAI API key
openai.api_key = OPENAI_API_KEY

# Authorization Functions
def start_google_auth(update: Update, context: CallbackContext):
    flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
    auth_url, _ = flow.authorization_url(prompt='consent')
    context.user_data['flow'] = flow
    update.message.reply_text(f"Please visit this link to authorize:\n{auth_url}\n"
                              "After authorizing, paste the code you receive here.")

def complete_google_auth(update: Update, context: CallbackContext):
    if 'flow' not in context.user_data:
        update.message.reply_text("Authorization process not started. Use /authorize first.")
        return
    flow = context.user_data['flow']
    code = update.message.text.strip()
    try:
        flow.fetch_token(code=code)
        creds = flow.credentials
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
        update.message.reply_text("Authorization successful! You're now connected to Google Calendar.")
    except Exception as e:
        update.message.reply_text(f"Authorization failed: {str(e)}")

def get_google_creds():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise Exception("User not authorized. Use /authorize to connect.")
    return creds

def get_calendar_service():
    creds = get_google_creds()
    service = build('calendar', 'v3', credentials=creds)
    return service

# Motivational Messages and Task Breakdown
def divide_task_into_steps(task_description):
    try:
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=f"Break down the task '{task_description}' into actionable and manageable steps:",
            max_tokens=150
        )
        return response.choices[0].text.strip()
    except Exception as e:
        return f"Couldn't process the task due to an error: {str(e)}"

# Reminder Functions
def schedule_event_reminders(context: CallbackContext):
    """Schedules reminders for upcoming events."""
    try:
        service = get_calendar_service()
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=10, singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            if not start:
                continue
            event_time = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
            reminder_time = event_time - datetime.timedelta(minutes=15)

            if reminder_time > datetime.datetime.utcnow():
                context.job_queue.run_once(
                    send_event_reminder,
                    when=(reminder_time - datetime.datetime.utcnow()).total_seconds(),
                    context={
                        "chat_id": context.job.context,
                        "event": event
                    }
                )
    except Exception as e:
        context.bot.send_message(chat_id=context.job.context, text=f"Failed to schedule reminders: {str(e)}")

def send_event_reminder(context: CallbackContext):
    """Sends a reminder for a specific event."""
    job_context = context.job.context
    chat_id = job_context["chat_id"]
    event = job_context["event"]

    summary = event.get('summary', 'No Title')
    description = event.get('description', 'No Description')
    motivational_message = "You’ve got this! Let’s tackle this event with full energy! 💪"
    breakdown_steps = divide_task_into_steps(description) if description != 'No Description' else "No steps provided."

    context.bot.send_message(
        chat_id=chat_id,
        text=f"🔔 Reminder: {summary}\n\nDescription: {description}\n\n{motivational_message}\n\nSteps:\n{breakdown_steps}"
    )

# Bot Setup
def main():
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher

    # Commands
    dp.add_handler(CommandHandler("start", lambda update, context: update.message.reply_text(
        "Hi! I'm your calendar bot. Use /authorize to connect your Google Calendar.")))
    dp.add_handler(CommandHandler("authorize", start_google_auth))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, complete_google_auth))

    # Job Queue for Event Reminders
    job_queue = updater.job_queue
    job_queue.run_repeating(schedule_event_reminders, interval=3600, first=0, context=123456789)  # Replace with your chat ID

    # Start the bot
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
