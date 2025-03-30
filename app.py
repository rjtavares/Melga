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


@app.route('/snooze/<int:task_id>/<int:days>', methods=['POST'])
def snooze_task(task_id, days):
    db = get_db()
    cursor = db.execute('SELECT id FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()

    if task:
        # Validate days input
        if days not in [1, 3, 7]:
            flash('Invalid snooze duration.', 'error')
            response = make_response(get_tasks())
            response.headers['HX-Trigger'] = 'showFlash'
            return response
            
        today = date.today()
        new_due_date = today + timedelta(days=days)
        new_due_date_str = new_due_date.strftime('%Y-%m-%d')

        db.execute('UPDATE tasks SET due_date = ? WHERE id = ?', (new_due_date_str, task_id))
        db.commit()
        
        # Create a more descriptive message
        day_str = "day" if days == 1 else "days"
        week_str = " (1 week)" if days == 7 else ""
        flash(f'Task snoozed for {days} {day_str}{week_str} until {new_due_date.strftime("%d/%m/%Y")}.', 'success')
    else:
        flash('Task not found.', 'error')

    # Return the updated task list partial for HTMX
    response = make_response(get_tasks())
    response.headers['HX-Trigger'] = 'showFlash'
    return response


@app.route('/flash-messages', methods=['GET'])
def get_flashed_messages_json():
    """Endpoint to fetch flash messages for HTMX."""
    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append({'category': category, 'message': message})
    return render_template('_flash_messages.html', messages=messages)


if __name__ == '__main__':
    # Ensure the db is initialized if it doesn't exist (optional, good for dev)
    # try:
    #     with open(DATABASE): pass
    # except IOError:
    #     print("Database not found, initializing...")
    #     init_db()

    app.run(debug=True, port=5001) # debug=True for development
