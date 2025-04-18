import click
from flask import Flask, render_template, request, g, make_response, get_flashed_messages, flash, json
from datetime import date, datetime, timedelta
import notifications  # Import the entire module instead of specific function
from db import get_db, get_task, get_activity_data
from dotenv import load_dotenv
import os

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_key_for_testing')  # Set a secret key for Flask sessions

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
    
    # Get activity data for the GitHub-style activity graph
    activity_data = get_activity_data()
    
    # Get the last 21 days as a list for display
    last_21_days = []
    for i in range(21):
        day = today - timedelta(days=20-i)
        day_str = day.strftime('%Y-%m-%d')
        # Format the date for display
        day_display = day.strftime('%d/%m')
        # Create activity info
        day_info = {
            'date': day_str,
            'display': day_display,
            'actions': activity_data[day_str]['actions'],
            'completions': activity_data[day_str]['completions'],
            'weekday': day.strftime('%a')[:1],  # First letter of weekday
            'is_today': day == today
        }
        last_21_days.append(day_info)

    return render_template('index.html', tasks=tasks, today=today, activity_data=last_21_days)


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

    # Get activity data for the GitHub-style activity graph
    activity_data = get_activity_data()
    
    # Get the last 21 days as a list for display
    last_21_days = []
    for i in range(21):
        day = today - timedelta(days=20-i)
        day_str = day.strftime('%Y-%m-%d')
        # Format the date for display
        day_display = day.strftime('%d/%m')
        # Create activity info
        day_info = {
            'date': day_str,
            'display': day_display,
            'actions': activity_data[day_str]['actions'],
            'completions': activity_data[day_str]['completions'],
            'weekday': day.strftime('%a')[:1],  # First letter of weekday
            'is_today': day == today
        }
        last_21_days.append(day_info)

    # If this is an HTMX request, only return the updated task list
    if 'HX-Request' in request.headers:
        # Return task list and activity graph
        response = make_response(render_template('_tasks.html', tasks=tasks, today=today))
        response.headers['HX-Trigger'] = json.dumps({
            'refreshActivityGraph': {
                'activity_data': last_21_days
            }
        })
        return response
        
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
    cursor = db.execute('SELECT completed, completion_date FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()
    if task:
        new_status = not task['completed']
        today = date.today()
        today_str = today.strftime('%Y-%m-%d')
        
        if new_status:  # If task is being marked as completed
            db.execute('UPDATE tasks SET completed = ?, completion_date = ? WHERE id = ?', 
                      (new_status, today_str, task_id))
        else:  # If task is being marked as pending
            db.execute('UPDATE tasks SET completed = ?, completion_date = NULL WHERE id = ?', 
                      (new_status, task_id))
        
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
    task = get_task(task_id)
    
    if not task:
        flash('Task not found.', 'error')
        return '', 400  # Bad request
    
    try:
        status_code = notifications.send_notification(task)  # Use the module reference
        if status_code == 200:
            flash('Notification sent successfully!', 'success')
        elif isinstance(status_code, str):
            flash(f'Failed to send notification. {status_code}', 'error')
        else:
            flash(f'Failed to send notification. Status code: {status_code}', 'error')
            
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
    task = get_task(task_id) # get_task now fetches next_action too

    if not task:
        flash('Task not found.', 'error')
        # Consider redirecting to index or showing a dedicated error page
        # For now, rendering index template with empty tasks as a fallback
        cursor = db.execute('SELECT id, description, due_date, completed FROM tasks ORDER BY due_date ASC')
        tasks_raw = cursor.fetchall()
        tasks = []
        today = date.today()
        for t in tasks_raw:
            task_dict_item = dict(t)
            try:
                due_date_obj = datetime.strptime(t['due_date'], '%Y-%m-%d').date()
                task_dict_item['due_date_display'] = due_date_obj.strftime('%d/%m/%Y')
                task_dict_item['is_overdue'] = not t['completed'] and due_date_obj < today
            except (ValueError, TypeError):
                task_dict_item['due_date_display'] = "Invalid Date"
                task_dict_item['is_overdue'] = False
            tasks.append(task_dict_item)
        response = make_response(render_template('index.html', tasks=tasks, today=today))
        response.headers['HX-Trigger'] = 'showFlash' # Trigger flash display if needed
        return response

    # Convert the task Row object to a dictionary to pass to the template
    # This dictionary will include 'id', 'description', 'due_date', 'completed', 'last_notification', 'next_action'
    task_dict = dict(task)

    # Fetch actions for the task
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
            action_date_obj = datetime.strptime(action['action_date'], '%Y-%m-%d').date()
            action_dict['action_date_display'] = action_date_obj.strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            action_dict['action_date_display'] = "Invalid Date"
        actions.append(action_dict)

    # Render the task history template with task details and actions
    return render_template('task_history.html', task=task_dict, actions=actions)


@app.route('/task/<int:task_id>/next_action', methods=['POST'])
def update_next_action(task_id):
    """Update the next_action for a specific task."""
    next_action_text = request.form.get('next_action', '').strip()
    db = get_db()
    try:
        db.execute('UPDATE tasks SET next_action = ? WHERE id = ?', (next_action_text, task_id))
        db.commit()
        # Fetch the updated task data to pass to the partial
        updated_task = get_task(task_id)
        if updated_task:
             # Return the VIEW partial to replace the edit form after saving
             return render_template('_next_action_view.html', task=dict(updated_task))
        else:
             # Handle case where task might have been deleted in the meantime
             return "Task not found", 404
    except Exception as e:
        db.rollback() # Rollback in case of error
        flash(f'Error updating next action: {str(e)}', 'error')
        # Return an error response, potentially triggering flash message display
        response = make_response("Error updating next action", 500)
        response.headers['HX-Trigger'] = 'showFlash'
        return response


@app.route('/task/<int:task_id>/edit_next_action', methods=['GET'])
def get_edit_next_action_form(task_id):
    """Serve the partial template containing the form to edit next_action."""
    task = get_task(task_id)
    if task:
        return render_template('_next_action_edit.html', task=dict(task))
    else:
        # Optionally return an error snippet or handle appropriately
        return "Task not found", 404


@app.route('/task/<int:task_id>/view_next_action', methods=['GET'])
def get_view_next_action(task_id):
    """Serve the partial template for viewing next_action."""
    task = get_task(task_id)
    if task:
        return render_template('_next_action_view.html', task=dict(task))
    else:
        return "Task not found", 404


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
    """Snooze a task, add an action entry, and optionally update next action."""
    action_description = request.form.get('action_description')
    next_action_text = request.form.get('next_action', '').strip() # Get optional next action
    
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
        
        # Update next action if provided
        if next_action_text:
             db.execute('UPDATE tasks SET next_action = ? WHERE id = ?', (next_action_text, task_id))

        # Add an action entry for the snooze
        today = date.today().strftime('%Y-%m-%d')
        # Determine day string for flash message
        day_str = "day" if days == 1 else "days"
        
        db.execute(
            'INSERT INTO task_actions (task_id, action_description, action_date) VALUES (?, ?, ?)',
            (task_id, action_description, today)
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


@app.route('/reset-date/<int:task_id>', methods=['POST'])
def reset_date(task_id):
    """Reset the due date of a task to today."""
    db = get_db()
    cursor = db.execute('SELECT id, description, due_date FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()

    if task:
        # Check if task is overdue
        today = date.today()
        today_str = today.strftime('%Y-%m-%d')
        
        try:
            due_date = date.fromisoformat(task['due_date'])
            if due_date < today:
                flash('Cannot reset date for overdue tasks.', 'error')
                response = make_response(get_tasks())
                response.headers['HX-Trigger'] = 'showFlash'
                return response
        except (ValueError, TypeError):
            # If date format is invalid, proceed with reset
            pass
        
        # Update the task
        db.execute('UPDATE tasks SET due_date = ? WHERE id = ?', (today_str, task_id))
        
        # Add an action entry for resetting the date
        db.execute(
            'INSERT INTO task_actions (task_id, action_description, action_date) VALUES (?, ?, ?)',
            (task_id, "Reset due date to today", today_str)
        )
        
        db.commit()
        flash(f'Due date for task reset to today ({today.strftime("%d/%m/%Y")}).', 'success')
    else:
        flash('Task not found.', 'error')

    # Return the updated task list partial for HTMX
    response = make_response(get_tasks())
    response.headers['HX-Trigger'] = 'showFlash'
    return response


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true' # <-- Change this line
    app.run(debug=debug_mode, port=5001) # debug=True for development
