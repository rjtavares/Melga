import datetime
import os.path
import pickle
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import timedelta

# Define the scopes
SCOPES = ['https://www.googleapis.com/auth/calendar.events.owned']

def authenticate_calendar(credentials_file='credentials.json'):
    """Authenticate to Google Calendar API using JSON credentials file."""
    creds = None
    
    # Check if token.pickle exists (stores access tokens)
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If credentials don't exist or are invalid, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return build('calendar', 'v3', credentials=creds)

def create_event(task: dict, start_time: datetime.datetime, duration: int = 30) -> dict:
    """
    Create a new event in the primary calendar.
    
    Args:
        task (dict): The task to create an event for.
        start_time (datetime.datetime): The start time of the event.
        duration (int, optional): The duration of the event in minutes. Defaults to 30.
    
    Returns:
        dict: The created event.
    """
    service = authenticate_calendar()
    event = {
        'summary': f'Task: {task["description"]}',
        'description': f'Next Action: {task["next_action"]}',
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'Europe/Lisbon',
        },
        'end': {
            'dateTime': (start_time + timedelta(minutes=duration)).isoformat(),
            'timeZone': 'Europe/Lisbon',
        },
        'reminders': {
            'useDefault': True,
        },
    }

    event = service.events().insert(calendarId='primary', body=event).execute()
    print(f'Event created: {event.get("htmlLink")}')
    return event