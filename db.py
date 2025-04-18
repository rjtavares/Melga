from flask import g
import sqlite3
from datetime import date, timedelta

DATABASE = 'tasks.db'

def get_db(flask=True):
    if flask:
        db = getattr(g, '_database', None)
        if db is None:
            db = g._database = sqlite3.connect(DATABASE)
            db.row_factory = sqlite3.Row # Return rows as dictionary-like objects
        return db
    else:
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        return db

def get_task(task_id, flask=True):
    db = get_db(flask=True)
    cursor = db.execute('SELECT id, description, due_date, completed, last_notification, next_action FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()
    return task

def get_overdue_tasks():
    db = get_db(flask=False)
    cursor = db.execute('SELECT id, description, due_date, completed, last_notification, next_action FROM tasks WHERE completed = 0 AND due_date < CURRENT_DATE')
    tasks = cursor.fetchall()
    return tasks

def set_last_notification(task, notification_date=None):
    """
    Sets last_notification for a task to provided date (or today is None is given)
    """
    today = date.today()
    
    db = get_db(flask=False)
    db.execute('UPDATE tasks SET last_notification = ? WHERE id = ?', (notification_date or today, task['id']))
    db.commit()

def get_activity_data():
    """
    Get activity data for the past 14 days for GitHub-style activity graph
    Returns a dictionary with:
    - date strings as keys (YYYY-MM-DD format)
    - dictionary values containing counts for 'actions' and 'completions'
    """
    # Initialize result with the past 14 days
    today = date.today()
    result = {}
    
    # Create entries for each of the last 14 days
    for i in range(14):
        day = today - timedelta(days=13-i)  # Start from 13 days ago
        day_str = day.strftime('%Y-%m-%d')
        result[day_str] = {"actions": 0, "completions": 0}
    
    # Get database connection
    db = get_db(flask=True)
    
    # Get task actions for the past 14 days
    start_date = (today - timedelta(days=13)).strftime('%Y-%m-%d')
    cursor = db.execute(
        'SELECT action_date, COUNT(*) as count FROM task_actions '
        'WHERE action_date >= ? GROUP BY action_date', 
        (start_date,)
    )
    
    for row in cursor.fetchall():
        action_date = row['action_date']
        # Only include dates within our 14-day window
        if action_date in result:
            result[action_date]["actions"] = row['count']
    
    # Get completed tasks for the past 14 days
    cursor = db.execute(
        'SELECT completion_date, COUNT(*) as count FROM tasks '
        'WHERE completion_date >= ? AND completion_date IS NOT NULL GROUP BY completion_date', 
        (start_date,)
    )
    
    for row in cursor.fetchall():
        completion_date = row['completion_date']
        # Only include dates within our 14-day window
        if completion_date in result:
            result[completion_date]["completions"] = row['count']
    
    return result