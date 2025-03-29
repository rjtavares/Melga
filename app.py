import sqlite3
import click
from flask import Flask, render_template, request, redirect, url_for, g, flash
from datetime import date, datetime

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
        task_dict['due_date_obj'] = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
        task_dict['is_overdue'] = not task['completed'] and task_dict['due_date_obj'] < today
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
            task_dict['due_date_obj'] = datetime.strptime(task['due_date'], '%Y-%m-%d').date()
            task_dict['is_overdue'] = not task['completed'] and task_dict['due_date_obj'] < today
        except (ValueError, TypeError):
             # Handle cases where due_date might be invalid or None temporarily
             task_dict['due_date_obj'] = None
             task_dict['is_overdue'] = False
        tasks.append(task_dict)

    # Render only the task list part
    return render_template('_tasks.html', tasks=tasks, today=today)


@app.route('/add', methods=['POST'])
def add_task():
    description = request.form['description']
    due_date_str = request.form['due_date']

    if not description or not due_date_str:
        flash('Description and Due Date are required!', 'error')
        # In a full HTMX response, we might return an error partial
        # For simplicity now, redirecting back to main page or returning the full task list
        return redirect(url_for('index')) # Or return get_tasks() if target is just the list

    try:
        # Ensure date is in YYYY-MM-DD format for SQLite
        datetime.strptime(due_date_str, '%Y-%m-%d')
    except ValueError:
        flash('Invalid date format. Please use YYYY-MM-DD.', 'error')
        return redirect(url_for('index')) # Or return get_tasks()

    db = get_db()
    db.execute('INSERT INTO tasks (description, due_date) VALUES (?, ?)',
               (description, due_date_str))
    db.commit()
    flash('Task added successfully!', 'success')

    # Return the updated task list partial for HTMX
    return get_tasks()


@app.route('/toggle/<int:task_id>', methods=['POST'])
def toggle_task(task_id):
    db = get_db()
    cursor = db.execute('SELECT completed FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()
    if task:
        new_status = not task['completed']
        db.execute('UPDATE tasks SET completed = ? WHERE id = ?', (new_status, task_id))
        db.commit()
    else:
        flash('Task not found.', 'error')

    # Return the updated task list partial for HTMX
    return get_tasks()


@app.route('/delete/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    db.commit()
    flash('Task deleted.', 'info')

    # Return the updated task list partial for HTMX
    # Or return an empty response with status 200 OK if the target handles removal
    # return '', 200
    return get_tasks() # Easiest for now, redraws the whole list


if __name__ == '__main__':
    # Ensure the db is initialized if it doesn't exist (optional, good for dev)
    # try:
    #     with open(DATABASE): pass
    # except IOError:
    #     print("Database not found, initializing...")
    #     init_db()

    app.run(debug=True) # debug=True for development
