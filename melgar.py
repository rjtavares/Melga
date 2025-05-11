from notifications import send_notification
from events import create_event
from db import get_overdue_tasks
import datetime

def get_event_time(hour: float):
    hour_int = int(hour)
    minute = int((hour - hour_int) * 60)
    today = datetime.datetime.now()
    return datetime.datetime(
        today.year, 
        today.month, 
        today.day, 
        hour_int, minute, 0
    )   

def main():
    """Run the notifications and create events for overdue tasks."""
    overdue_tasks = get_overdue_tasks()

    event_time_1 = get_event_time(13)
    event_time_2 = get_event_time(18)

    notifications_sent = 0
    events_created = 0
    for task in overdue_tasks:
        status = send_notification(task)
        if status == 200:
            notifications_sent += 1

        event_1 = create_event(task, event_time_1)
        event_2 = create_event(task, event_time_2)

        if event_1 and event_2:
            events_created += 1
        else:
            if not event_1:
                print(f"Failed to create event for task {task['id']} at {event_time_1}")
            if not event_2:
                print(f"Failed to create event for task {task['id']} at {event_time_2}")

    print(f"Successfully sent {notifications_sent} notification(s) for overdue tasks out of {len(overdue_tasks)} tasks.")
    print(f"Successfully created {events_created} event(s) for overdue tasks out of {len(overdue_tasks)} tasks.")

if __name__ == "__main__":
    exit(main())
