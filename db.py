from flask import g
import sqlite3
from datetime import date, timedelta, datetime
import random

DATABASE = 'tasks.db'

# Date format constants
DATE_DB_FORMAT = '%Y-%m-%d'  # Format for storing dates in the database
DATE_DISPLAY_FORMAT = '%d/%m/%Y'  # Default format for displaying dates to users
DATE_DISPLAY_SHORT = '%d %b %Y'  # Short format with month name

def format_date(date_obj, format_str=DATE_DISPLAY_FORMAT):
    """Convert a date object to a formatted string."""
    if not date_obj:
        return None
    return date_obj.strftime(format_str)

def parse_date(date_str, format_str=DATE_DB_FORMAT):
    """Parse a date string into a date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, format_str).date()
    except ValueError:
        return None

def get_db_date(date_obj=None):
    """Convert a date object to database format string."""
    if date_obj is None:
        date_obj = date.today()
    return format_date(date_obj, DATE_DB_FORMAT)

def get_display_date(date_str, short=False):
    """Convert a database date string to display format."""
    if not date_str:
        return "Unknown Date"
    
    date_obj = parse_date(date_str)
    if not date_obj:
        return "Invalid Date"
    
    format_str = DATE_DISPLAY_SHORT if short else DATE_DISPLAY_FORMAT
    return format_date(date_obj, format_str)

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
    cursor = db.execute('SELECT id, description, due_date, completed, last_notification, next_action, priority FROM tasks WHERE id = ?', (task_id,))
    task = dict(cursor.fetchone())
    
    # Format dates and check overdue status
    due_date = parse_date(task['due_date'])
    task['due_date_display'] = format_date(due_date)
    task['is_overdue'] = due_date < date.today() and not task['completed']

    return task

def get_overdue_tasks():
    db = get_db(flask=False)
    cursor = db.execute('SELECT * FROM tasks WHERE completed = 0 AND due_date < CURRENT_DATE')
    tasks = [dict(x) for x in cursor.fetchall()]
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
    start_date = get_db_date(today - timedelta(days=days-1))
    actions = db.execute(
        'SELECT action_date, COUNT(*) as count FROM task_actions '
        'WHERE action_date >= ? GROUP BY action_date', 
        (start_date,)
    ).fetchall()
    
    # Get notes for the period
    notes = db.execute(
        'SELECT created_date, COUNT(*) as count FROM notes '
        'WHERE created_date >= ? GROUP BY created_date', 
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
    notes_dict = {row['created_date']: row['count'] for row in notes}

    result = {}
    # Create entries for each of the days
    for i in range(days):
        day = today - timedelta(days=i) 
        day_str = get_db_date(day)

        actions_date = actions_dict.get(day_str, 0)
        task_completions_date = task_completions_dict.get(day_str, 0)
        goal_completions_date = goal_completions_dict.get(day_str, 0)
        notes_date = notes_dict.get(day_str, 0)

        result[day_str] = {"actions": actions_date+notes_date,
                           "completions": task_completions_date+goal_completions_date}
    
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
        return dict(goal)
    return None

def get_tasks(flask=True):
    db = get_db(flask=flask)
    cursor = db.execute('SELECT id, description, due_date, completed, goal_id, completion_date, next_action, priority FROM tasks ORDER BY due_date ASC')
    tasks_raw = cursor.fetchall()

    tasks = []
    today = date.today()
    for task in tasks_raw:
        task_dict = dict(task) # Convert Row object to dict
        
        # Check if completion date is earlier than today
        if task['completion_date']:
            completion_date_obj = parse_date(task['completion_date'])
            earlier_than_today = completion_date_obj and completion_date_obj < today
        else:
            earlier_than_today = False
        
        if not earlier_than_today:
            # Parse the due date and format it for display
            due_date_obj = parse_date(task['due_date'])

            if due_date_obj:
                # Format for display (DD/MMM)
                task_dict['due_date_display'] = format_date(due_date_obj, '%d/%b')
                task_dict['is_overdue'] = not task['completed'] and due_date_obj < today
            else:
                task_dict['due_date_display'] = "Invalid Date"
                task_dict['is_overdue'] = False
                
            tasks.append(task_dict)
    
    return tasks

def get_priority_task():
    """Get the highest priority task with the earliest due date."""
    db = get_db()
    # Query for incomplete tasks with priority=1, ordered by due date
    cursor = db.execute(
        'SELECT id, description, due_date, next_action FROM tasks '
        'WHERE completed = 0 AND priority = 1 '
        'ORDER BY due_date ASC LIMIT 1'
    )
    task = cursor.fetchone()
    
    if not task:
        return None
    
    task_dict = dict(task)
    
    # Format the due date for display
    due_date_obj = parse_date(task['due_date'])
    if due_date_obj:
        task_dict['due_date_display'] = format_date(due_date_obj, '%d/%b')
    else:
        task_dict['due_date_display'] = "Unknown"
    
    return task_dict

def get_actions(task_id):
    db = get_db()
    cursor = db.execute('SELECT id, action_description, action_date FROM task_actions WHERE task_id = ? ORDER BY action_date DESC', (task_id,))
    actions_raw = cursor.fetchall()

    actions = []
    for action in actions_raw:
        action_dict = dict(action)
        action_dict['action_date_display'] = get_display_date(action['action_date'])
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
        # Format the date using our utility function
        note_dict['created_date'] = get_display_date(note['created_date'], short=True)
        
        # Truncate note preview
        if len(note_dict['note']) > 150:
            note_dict['note'] = note_dict['note'][:150] + '...'
            
        notes.append(note_dict)
    
    return notes

def insert_action(task_id, action_description, action_date):
    db = get_db()
    # Ensure action_date is in database format
    if isinstance(action_date, date):
        action_date = get_db_date(action_date)
    db.execute(
        'INSERT INTO task_actions (task_id, action_description, action_date) VALUES (?, ?, ?)',
        (task_id, action_description, action_date)
    )
    db.commit()
    return True

def delete_task(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    db.commit()
    return True

def delete_action(action_id):
    db = get_db()
    db.execute('DELETE FROM task_actions WHERE id = ?', (action_id,))
    db.commit()
    return True

def delete_note(note_id):
    db = get_db()
    db.execute('DELETE FROM notes WHERE id = ?', (note_id,))
    db.commit()
    return True

def update_task(task_id, task_data):
    update_table('tasks', task_id, task_data)
    return True

def update_note(note_id, note_data):
    update_table('notes', note_id, note_data)
    return True

def update_goal(goal_id, goal_data):
    update_table('goals', goal_id, goal_data)
    return True

def update_table(table, id, data):
    db = get_db()
    try:
        for key, value in data.items():
            sql = f'UPDATE {table} SET {key} = ? WHERE id = ?'
            db.execute(sql, (value, id))
        db.commit()
    except Exception as e:
        db.rollback() # Rollback in case of error
        raise e


def insert_goal(description, created_date, target_date):
    db = get_db()
    # Ensure dates are in database format
    if isinstance(created_date, date):
        created_date = get_db_date(created_date)
    if isinstance(target_date, date):
        target_date = get_db_date(target_date)
        
    db.execute(
        'INSERT INTO goals (description, created_date, target_date, completed) VALUES (?, ?, ?, 0)',
        (description, created_date, target_date)
    )
    db.commit()
    return True

def insert_note(title, note_content, note_type, created_date):
    db = get_db()
    # Ensure created_date is in database format
    if isinstance(created_date, date):
        created_date = get_db_date(created_date)
        
    db.execute(
        'INSERT INTO notes (title, note, type, created_date) VALUES (?, ?, ?, ?)',
        (title, note_content, note_type, created_date)
    )
    db.commit()
    return True

def insert_task(description, due_date, goal_id=None):
    db = get_db()
    # Ensure due_date is in database format
    if isinstance(due_date, date):
        due_date = get_db_date(due_date)

    created_date = get_db_date()  # Use today's date as created date    
    
    db.execute(
        'INSERT INTO tasks (description, due_date, goal_id, created_date) VALUES (?, ?, ?, ?)',
        (description, due_date, goal_id, created_date)
    )
    
    db.commit()
    return True

# --- Random Things To Do Functions ---

def get_random_thing(thing_id=None):
    '''
    Get a random thing to do from the database.
    If thing_id is provided, get that specific thing.
    Otherwise, get a random random thing to do.
    '''
    db = get_db()
    if thing_id is not None:
        cursor = db.execute('SELECT id, description, completed, completion_date, link FROM random_things_to_do WHERE id = ?', (thing_id,))
        thing = cursor.fetchone()
    else:
        # Fetch a random thing if no id is provided
        cursor = db.execute('SELECT id FROM random_things_to_do')
        all_ids = [row[0] for row in cursor.fetchall()]
        if not all_ids:
            return None # No random things in the database
        random_id = random.choice(all_ids)
        cursor = db.execute('SELECT id, description, completed, completion_date, link FROM random_things_to_do WHERE id = ?', (random_id,))
        thing = cursor.fetchone()

    if thing:
        return dict(thing)
    return None

def get_random_things():
    db = get_db()
    cursor = db.execute('SELECT id, description, completed, completion_date, link FROM random_things_to_do ORDER BY id DESC')
    things_raw = cursor.fetchall()
    
    things = []
    for thing in things_raw:
        thing_dict = dict(thing)
        # Format the completion date if it exists
        if thing_dict['completion_date']:
            thing_dict['completion_date_display'] = get_display_date(thing_dict['completion_date'], short=True)
        things.append(thing_dict)
    
    return things

def insert_random_thing(description, link=None):
    db = get_db()
    db.execute(
        'INSERT INTO random_things_to_do (description, link, completed) VALUES (?, ?, 0)',
        (description, link)
    )
    db.commit()
    return True

def toggle_random_thing(thing_id):
    db = get_db()
    thing = get_random_thing(thing_id)
    if thing:
        new_status = not thing['completed']
        today = date.today()
        
        if new_status:  # If thing is being marked as completed
            db.execute(
                'UPDATE random_things_to_do SET completed = ?, completion_date = ? WHERE id = ?',
                (new_status, get_db_date(today), thing_id)
            )
        else:  # If thing is being marked as pending
            db.execute(
                'UPDATE random_things_to_do SET completed = ?, completion_date = NULL WHERE id = ?',
                (new_status, thing_id)
            )
        db.commit()
        return True
    return False

def delete_random_thing(thing_id):
    db = get_db()
    db.execute('DELETE FROM random_things_to_do WHERE id = ?', (thing_id,))
    db.commit()
    return True