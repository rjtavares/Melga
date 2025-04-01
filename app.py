import sqlite3
import click
import requests
from flask import Flask, render_template, request, g, make_response, get_flashed_messages, flash
from datetime import date, datetime, timedelta

DATABASE = 'tasks.db'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your secret key' # Important for flashing messages

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row # Return rows as dictionary-like objects
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

@app.cli.command('init-db')
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')

@app.route('/')
def index():
    db = get_db()
    cursor = db.execute('SELECT id, description, due_date, completed FROM tasks ORDER BY due_date ASC')
    tasks_raw = cursor.fetchall()

    tasks = []
    today = date.today()
    for task in tasks_raw:
        task_dict = dict(task) # Convert Row object to dict
        try:
            # Parse DB date (YYYY-MM-DD)
            due_date_obj = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
            # Format for display (DD/MM/YYYY)
            task_dict['due_date_display'] = due_date_obj.strftime('%d/%m/%Y')
            task_dict['is_overdue'] = not task['completed'] and due_date_obj < today
        except (ValueError, TypeError):
            task_dict['due_date_display'] = "Invalid Date"
            task_dict['is_overdue'] = False
        tasks.append(task_dict)

    return render_template('index.html', tasks=tasks, today=today)


# --- HTMX Routes ---

@app.route('/tasks', methods=['GET'])
def get_tasks():
    """Endpoint to fetch the task list partial for HTMX updates."""
    db = get_db()
    cursor = db.execute('SELECT id, description, due_date, completed FROM tasks ORDER BY due_date ASC')
    tasks_raw = cursor.fetchall()

    tasks = []
    today = date.today()
    for task in tasks_raw:
        task_dict = dict(task) # Convert Row object to dict
        try:
            # Parse DB date (YYYY-MM-DD)
            due_date_obj = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
            # Format for display (DD/MM/YYYY)
            task_dict['due_date_display'] = due_date_obj.strftime('%d/%m/%Y')
            task_dict['is_overdue'] = not task['completed'] and due_date_obj < today
        except (ValueError, TypeError):
            task_dict['due_date_display'] = "Invalid Date"
            task_dict['is_overdue'] = False
        tasks.append(task_dict)

    # Render only the task list part
    return render_template('_tasks.html', tasks=tasks, today=today)


@app.route('/add', methods=['POST'])
def add_task():
    description = request.form['description']
    due_date_str_input = request.form['due_date'] # Input is YYYY-MM-DD from HTML date input

    if not description or not due_date_str_input:
        flash('Description and Due Date are required!', 'error')
        return get_tasks() # Return updated list even on error to show flash

    try:
        # Parse the input date (YYYY-MM-DD)
        due_date_db_format = datetime.strptime(due_date_str_input, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'error')
        return get_tasks() # Return updated list to show flash

    db = get_db()
    db.execute('INSERT INTO tasks (description, due_date) VALUES (?, ?)',
               (description, due_date_db_format))
    db.commit()
    flash('Task added successfully!', 'success')

    # Return the updated task list partial for HTMX
    response = make_response(get_tasks())
    response.headers['HX-Trigger'] = 'showFlash'
    return response


@app.route('/toggle/<int:task_id>', methods=['POST'])
def toggle_task(task_id):
    db = get_db()
    cursor = db.execute('SELECT completed FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()
    if task:
        new_status = not task['completed']
        db.execute('UPDATE tasks SET completed = ? WHERE id = ?', (new_status, task_id))
        db.commit()
        status_text = "completed" if new_status else "marked as pending"
        flash(f'Task {status_text}.', 'success')
    else:
        flash('Task not found.', 'error')

    # Return the updated task list partial for HTMX
    response = make_response(get_tasks())
    response.headers['HX-Trigger'] = 'showFlash'
    return response


@app.route('/delete/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    db.commit()
    flash('Task deleted.', 'info')

    # Return the updated task list partial for HTMX
    response = make_response(get_tasks())
    response.headers['HX-Trigger'] = 'showFlash'
    return response


@app.route('/notify/<int:task_id>', methods=['POST'])
def notify_task(task_id):
    """Send a notification about the task to ntfy."""
    NTFY_TOPIC = "alertas_para_tlm_do_ricardinho"
    NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"
    
    db = get_db()
    cursor = db.execute('SELECT description, due_date, completed FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()
    
    if not task:
        flash('Task not found.', 'error')
        return '', 400  # Bad request
    
    # Format the due date for display
    try:
        due_date_obj = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
        due_date_display = due_date_obj.strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        due_date_display = "Invalid Date"
    
    # Prepare notification content
    status = "COMPLETED" if task['completed'] else "PENDING"
    title = f"Task: {task['description']}"
    message = f"Due: {due_date_display}\nStatus: {status}"
    priority = "high" if not task['completed'] and due_date_obj < date.today() else "default"
    
    # Send notification to ntfy
    try:
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
            flash('Notification sent successfully!', 'success')
        else:
            flash(f'Failed to send notification. Status code: {response.status_code}', 'error')
            
    except Exception as e:
        flash(f'Error sending notification: {str(e)}', 'error')
    
    # Return a response with HX-Trigger to show flash messages
    response = make_response('', 200)
    response.headers['HX-Trigger'] = 'showFlash'
    return response


# --- Task History Routes ---

@app.route('/task/<int:task_id>')
def task_history(task_id):
    """Show task history page with all actions for a specific task."""
    db = get_db()
    
    # Get task details
    cursor = db.execute('SELECT id, description, due_date, completed FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()
    
    if not task:
        flash('Task not found.', 'error')
        return render_template('index.html')
    
    # Format task data
    task_dict = dict(task)
    today = date.today()
    try:
        # Parse DB date (YYYY-MM-DD)
        due_date_obj = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
        # Format for display (DD/MM/YYYY)
        task_dict['due_date_display'] = due_date_obj.strftime('%d/%m/%Y')
        task_dict['is_overdue'] = not task['completed'] and due_date_obj < today
    except (ValueError, TypeError):
        task_dict['due_date_display'] = "Invalid Date"
        task_dict['is_overdue'] = False
    
    # Get task actions
    cursor = db.execute(
        'SELECT id, action_description, action_date FROM task_actions WHERE task_id = ? ORDER BY action_date DESC',
        (task_id,)
    )
    actions_raw = cursor.fetchall()
    
    # Format actions data
    actions = []
    for action in actions_raw:
        action_dict = dict(action)
        try:
            # Parse DB date (YYYY-MM-DD)
            action_date_obj = datetime.strptime(action['action_date'], '%Y-%m-%d').date()
            # Format for display (DD/MM/YYYY)
            action_dict['action_date_display'] = action_date_obj.strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            action_dict['action_date_display'] = "Invalid Date"
        actions.append(action_dict)
    
    return render_template('task_history.html', task=task_dict, actions=actions)


@app.route('/task/<int:task_id>/add-action', methods=['POST'])
def add_task_action(task_id):
    """Add a new action to a task."""
    action_description = request.form.get('action_description')
    
    if not action_description:
        flash('Action description is required!', 'error')
        return '', 400
    
    # Verify task exists
    db = get_db()
    cursor = db.execute('SELECT id FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()
    
    if not task:
        flash('Task not found.', 'error')
        return '', 404
    
    # Add the action
    today = date.today().strftime('%Y-%m-%d')
    db.execute(
        'INSERT INTO task_actions (task_id, action_description, action_date) VALUES (?, ?, ?)',
        (task_id, action_description, today)
    )
    db.commit()
    
    # Get updated actions list
    cursor = db.execute(
        'SELECT id, action_description, action_date FROM task_actions WHERE task_id = ? ORDER BY action_date DESC',
        (task_id,)
    )
    actions_raw = cursor.fetchall()
    
    # Format actions data
    actions = []
    for action in actions_raw:
        action_dict = dict(action)
        try:
            # Parse DB date (YYYY-MM-DD)
            action_date_obj = datetime.strptime(action['action_date'], '%Y-%m-%d').date()
            # Format for display (DD/MM/YYYY)
            action_dict['action_date_display'] = action_date_obj.strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            action_dict['action_date_display'] = "Invalid Date"
        actions.append(action_dict)
    
    # Return the updated actions list partial
    return render_template('_actions.html', actions=actions)


@app.route('/snooze-modal/<int:task_id>/<int:days>', methods=['GET'])
def snooze_modal(task_id, days):
    """Show a modal dialog to enter action before snoozing a task."""
    # Validate days input
    if days not in [1, 3, 7]:
        flash('Invalid snooze duration.', 'error')
        return '', 400
    
    # Format text for display
    day_str = "day" if days == 1 else "days"
    days_text = f"{days} {day_str}"
    if days == 7:
        days_text += " (1 week)"
    
    return render_template('_snooze_modal.html', task_id=task_id, days=days, days_text=days_text)


@app.route('/snooze/<int:task_id>/<int:days>', methods=['POST'])
def snooze_task(task_id, days):
    """Snooze a task and add an action entry explaining why."""
    action_description = request.form.get('action_description')
    
    # Don't allow snoozing without an action description
    if not action_description:
        flash('Action description is required to snooze a task.', 'error')
        response = make_response(get_tasks())
        response.headers['HX-Trigger'] = 'showFlash'
        return response
    
    db = get_db()
    cursor = db.execute('SELECT id, due_date FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()

    if task:
        # Validate days input
        if days not in [1, 3, 7]:
            flash('Invalid snooze duration.', 'error')
            response = make_response(get_tasks())
            response.headers['HX-Trigger'] = 'showFlash'
            return response
            
        # Get current due date or use today if no due date exists
        current_due_date = date.today()
        if task['due_date']:
            try:
                current_due_date = date.fromisoformat(task['due_date'])
            except ValueError:
                # If due date is invalid, fall back to today
                pass
                
        # Add days to the current due date
        new_due_date = current_due_date + timedelta(days=days)
        new_due_date_str = new_due_date.strftime('%Y-%m-%d')

        db.execute('UPDATE tasks SET due_date = ? WHERE id = ?', (new_due_date_str, task_id))
        
        # Add an action entry for the snooze
        today = date.today().strftime('%Y-%m-%d')
        day_str = "day" if days == 1 else "days"
        snooze_note = f"Snoozed for {days} {day_str} until {new_due_date.strftime('%d/%m/%Y')}"
        
        db.execute(
            'INSERT INTO task_actions (task_id, action_description, action_date) VALUES (?, ?, ?)',
            (task_id, f"{action_description} ({snooze_note})", today)
        )
        
        db.commit()
        
        # Create a more descriptive message
        week_str = " (1 week)" if days == 7 else ""
        flash(f'Task snoozed for {days} {day_str}{week_str} until {new_due_date.strftime("%d/%m/%Y")}.', 'success')
    else:
        flash('Task not found.', 'error')

    # Return the updated task list partial for HTMX
    response = make_response(get_tasks())
    response.headers['HX-Trigger'] = 'showFlash'
    return response


@app.route('/flash-messages')
def get_flash_messages():
    """Endpoint to fetch flash messages for HTMX updates."""
    messages = get_flashed_messages(with_categories=True)
    messages_dicts = [{"category": category, "message": message} for category, message in messages]
    return render_template('_flash_messages.html', messages=messages_dicts)


@app.route('/task/action/<int:action_id>/delete', methods=['DELETE'])
def delete_action(action_id):
    """Delete a specific action from a task."""
    db = get_db()
    
    # First, get the task_id to return to the correct task after deletion
    cursor = db.execute('SELECT task_id FROM task_actions WHERE id = ?', (action_id,))
    action = cursor.fetchone()
    
    if not action:
        return render_template('_actions.html', actions=[]), 404
    
    task_id = action['task_id']
    
    # Delete the action
    db.execute('DELETE FROM task_actions WHERE id = ?', (action_id,))
    db.commit()
    
    # Get updated actions list
    cursor = db.execute(
        'SELECT id, action_description, action_date FROM task_actions WHERE task_id = ? ORDER BY action_date DESC',
        (task_id,)
    )
    actions_raw = cursor.fetchall()
    
    # Format actions data
    actions = []
    for action in actions_raw:
        action_dict = dict(action)
        try:
            # Parse DB date (YYYY-MM-DD)
            action_date_obj = datetime.strptime(action['action_date'], '%Y-%m-%d').date()
            # Format for display (DD/MM/YYYY)
            action_dict['action_date_display'] = action_date_obj.strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            action_dict['action_date_display'] = "Invalid Date"
        actions.append(action_dict)
    
    # Return the updated actions list partial
    return render_template('_actions.html', actions=actions)


if __name__ == '__main__':
    # Ensure the db is initialized if it doesn't exist (optional, good for dev)
    # try:
    #     with open(DATABASE): pass
    # except IOError:
    #     print("Database not found, initializing...")
    #     init_db()

    app.run(debug=True, port=5001) # debug=True for development
