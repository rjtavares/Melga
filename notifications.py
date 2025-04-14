import requests
import os
from datetime import datetime, date
from db import get_overdue_tasks, set_last_notification
from dotenv import load_dotenv

load_dotenv()

def send_notification(task):
    NTFY_TOPIC = os.getenv('NTFY_TOPIC')
    NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

    # Check if last notification was today
    today = date.today()

    if task['last_notification']:
        last_notif_date = datetime.strptime(task['last_notification'], '%Y-%m-%d').date()
        if last_notif_date >= today:
            return 'Notification already sent.'
    
    # Format the due date for display
    try:
        due_date_obj = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
        due_date_display = due_date_obj.strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        due_date_display = "Invalid Date"

    # Prepare notification content
    status = "COMPLETED" if task['completed'] else "PENDING"
    title = f"Task Due: {task['description']}"
    message = f"Due Date: {due_date_display}"
    if task['next_action']: # Check if next_action exists and is not empty
        message += f"\nNext Action: {task['next_action']}"
    message += f"\nStatus: {status}"
    priority = "high" if not task['completed'] and due_date_obj < date.today() else "default"
    
    # Send notification to ntfy
    response = requests.post(
        NTFY_URL,
        data=message,
        headers={
            "Title": title,
            "Priority": priority,
            "Tags": "calendar,phone",
        }
    )

    if response.status_code == 200:
        set_last_notification(task)
    
    return response.status_code

def notify_overdue():
    overdue_tasks = get_overdue_tasks()
    notifications_sent = 0
    for task in overdue_tasks:
        status = send_notification(task)
        if status == 200:
            notifications_sent += 1
    return len(overdue_tasks), notifications_sent

def main():
    """Run the notifications for overdue tasks."""
    try:
        count, sent = notify_overdue()
        print(f"Successfully sent {sent} notification(s) for overdue tasks out of {count} tasks.")
        return 0
    except Exception as e:
        print(f"Error sending notifications: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
