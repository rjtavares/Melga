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

def get_activity_data(days=21, flask=True):
    """
    Get activity data for the past 21 days for GitHub-style activity graph
    Returns a dictionary with:
    - date strings as keys (YYYY-MM-DD format)
    - dictionary values containing counts for 'actions' and 'completions'
    """
    # Initialize result with the period
    today = date.today()
    
    # Get database connection
    db = get_db(flask=flask)
    
    # Get task actions for the period
    start_date = (today - timedelta(days=days-1)).strftime('%Y-%m-%d')
    actions = db.execute(
        'SELECT action_date, COUNT(*) as count FROM task_actions '
        'WHERE action_date >= ? GROUP BY action_date', 
        (start_date,)
    ).fetchall()
    
    # Get completed tasks for the period
    task_completions = db.execute(
        'SELECT completion_date, COUNT(*) as count FROM tasks '
        'WHERE completion_date >= ? AND completed = 1 GROUP BY completion_date', 
        (start_date,)
    ).fetchall()
    
    # Get completed goals for the period
    goal_completions = db.execute(
        'SELECT completion_date, COUNT(*) as count FROM goals '
        'WHERE completion_date >= ? AND completed = 1 GROUP BY completion_date', 
        (start_date,)
    ).fetchall()

    result = {}
    # Create entries for each of the days
    for i in range(days):
        day = today - timedelta(days=i) 
        day_str = day.strftime('%Y-%m-%d')

        actions_date = actions.get(day_str, {'count': 0})['count']
        task_completions_date = task_completions.get(day_str, {'count': 0})['count']
        goal_completions_date = goal_completions.get(day_str, {'count': 0})['count']

        result[day_str] = {"actions": actions_date, "completions": task_completions_date+goal_completions_date}
    
    return result

def get_current_goal():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT id, description, created_date, target_date, completed, completion_date
        FROM goals
        WHERE completed = 0
        ORDER BY id DESC
        LIMIT 1
    ''')
    goal = cursor.fetchone()
    if goal:
        return {
            'id': goal[0],
            'description': goal[1],
            'created_date': goal[2],
            'target_date': goal[3],
            'completed': bool(goal[4]),
            'completion_date': goal[5]
        }
    return None
