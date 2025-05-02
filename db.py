from flask import g
import sqlite3
from datetime import date, timedelta, datetime

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

def get_task(task_id):
    db = get_db()
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

    # Convert the list results to dictionaries for easier lookup
    actions_dict = {row['action_date']: row['count'] for row in actions}
    task_completions_dict = {row['completion_date']: row['count'] for row in task_completions}
    goal_completions_dict = {row['completion_date']: row['count'] for row in goal_completions}

    result = {}
    # Create entries for each of the days
    for i in range(days):
        day = today - timedelta(days=i) 
        day_str = day.strftime('%Y-%m-%d')

        actions_date = actions_dict.get(day_str, 0)
        task_completions_date = task_completions_dict.get(day_str, 0)
        goal_completions_date = goal_completions_dict.get(day_str, 0)

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

def get_tasks(flask=True):
    db = get_db(flask=flask)
    cursor = db.execute('SELECT id, description, due_date, completed, goal_id FROM tasks ORDER BY due_date ASC')
    tasks_raw = cursor.fetchall()

    tasks = []
    today = date.today()
    for task in tasks_raw:
        task_dict = dict(task) # Convert Row object to dict
        try:
            # Parse DB date (YYYY-MM-DD)
            due_date_obj = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
            # Format for display (DD/MMM)
            task_dict['due_date_display'] = due_date_obj.strftime('%d/%b')
            task_dict['is_overdue'] = not task['completed'] and due_date_obj < today
        except (ValueError, TypeError):
            task_dict['due_date_display'] = "Invalid Date"
            task_dict['is_overdue'] = False
        tasks.append(task_dict)
    return tasks

def get_actions(task_id):
    db = get_db()
    cursor = db.execute('SELECT id, action_description, action_date FROM task_actions WHERE task_id = ? ORDER BY action_date DESC', (task_id,))
    actions_raw = cursor.fetchall()

    actions = []
    for action in actions_raw:
        action_dict = dict(action)
        try:
            action_date_obj = datetime.strptime(action['action_date'], '%Y-%m-%d').date()
            action_dict['action_date_display'] = action_date_obj.strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            action_dict['action_date_display'] = "Invalid Date"
        actions.append(action_dict)
    return actions

def get_action(action_id):
    db = get_db()
    cursor = db.execute('SELECT id, action_description, action_date, task_id FROM task_actions WHERE id = ?', (action_id,))
    action = cursor.fetchone()
    return dict(action)

def get_note(note_id):
    db = get_db()
    cursor = db.execute('SELECT id, title, note, type, created_date FROM notes WHERE id = ?', (note_id,))
    note = cursor.fetchone()
    return dict(note)

def get_notes():
    db = get_db()
    cursor = db.execute('SELECT id, title, note, type, created_date FROM notes ORDER BY created_date DESC')
    notes_raw = cursor.fetchall()
    
    notes = []
    for note in notes_raw:
        note_dict = dict(note)
        # Format the date
        try:
            created_date_obj = datetime.strptime(note['created_date'], '%Y-%m-%d').date()
            note_dict['created_date'] = created_date_obj.strftime('%d %b %Y')
        except (ValueError, TypeError):
            note_dict['created_date'] = "Unknown Date"
        
        # Truncate note preview
        if len(note_dict['note']) > 150:
            note_dict['note'] = note_dict['note'][:150] + '...'
            
        notes.append(note_dict)
    
    return notes
