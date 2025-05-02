from flask import Flask, render_template, request, g, make_response, get_flashed_messages, flash, json, redirect, url_for
from datetime import date, datetime, timedelta
import notifications  # Import the entire module instead of specific function
from db import get_db, get_task, get_activity_data, get_current_goal, get_tasks, get_actions
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

@app.route('/')
def index():
    today = date.today()
    tasks = get_tasks()
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
            'actions': activity_data.get(day_str, {'actions': 0, 'completions': 0})['actions'],
            'completions': activity_data.get(day_str, {'actions': 0, 'completions': 0})['completions'],
            'weekday': day.strftime('%a')[:1],  # First letter of weekday
            'is_today': day == today
        }
        last_21_days.append(day_info)

    current_goal = get_current_goal()

    return render_template('index.html', tasks=tasks, today=today, activity_data=last_21_days, current_goal=current_goal)


# --- HTMX Routes ---

def make_task_list():
    """Endpoint to fetch the task list partial for HTMX updates."""
    tasks = get_tasks()
    current_goal = get_current_goal()
    return render_template('_tasks.html', tasks=tasks, current_goal=current_goal)

@app.route('/add', methods=['POST'])
def add_task():
    description = request.form['description']
    due_date_str_input = request.form['due_date'] # Input is YYYY-MM-DD from HTML date input
    link_to_goal = request.form.get('link_goal')

    try:
        # Parse the input date (YYYY-MM-DD)
        due_date_db_format = datetime.strptime(due_date_str_input, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'error')
        return make_task_list() # Return updated list to show flash

    db = get_db()
    goal_id = None
    if link_to_goal:
        current_goal = get_current_goal()
        if current_goal:
            goal_id = current_goal['id']
    if goal_id is not None:
        db.execute('INSERT INTO tasks (description, due_date, goal_id) VALUES (?, ?, ?)',
                   (description, due_date_db_format, goal_id))
    else:
        db.execute('INSERT INTO tasks (description, due_date) VALUES (?, ?)',
                   (description, due_date_db_format))
    db.commit()
    flash('Task added successfully!', 'success')

    # Return the updated task list partial for HTMX
    response = make_response(make_task_list())
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
    response = make_response(make_task_list())
    response.headers['HX-Trigger'] = 'showFlash'
    return response


@app.route('/delete/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    db.commit()
    flash('Task deleted.', 'info')

    # Return the updated task list partial for HTMX
    response = make_response(make_task_list())
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
    task = get_task(task_id) # get_task now fetches next_action too

    if not task:
        return redirect(url_for('index'))

    # Convert the task Row object to a dictionary to pass to the template
    task_dict = dict(task)

    actions = get_actions(task_id)

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
    
    task = get_task(task_id)

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

    actions = get_actions(task_id)
    
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
        response = make_response(make_task_list())
        response.headers['HX-Trigger'] = 'showFlash'
        return response
    
    db = get_db()
    cursor = db.execute('SELECT id, due_date FROM tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()

    if task:
        # Validate days input
        if days not in [1, 3, 7]:
            flash('Invalid snooze duration.', 'error')
            response = make_response(make_task_list())
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
    response = make_response(make_task_list())
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
                response = make_response(make_task_list())
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
    response = make_response(make_task_list())
    response.headers['HX-Trigger'] = 'showFlash'
    return response


@app.route('/goal/edit')
def edit_goal():
    current_goal = get_current_goal()
    return render_template('_goal_edit.html', current_goal=current_goal)

@app.route('/goal/view')
def view_goal():
    current_goal = get_current_goal()
    return render_template('_goal_view.html', current_goal=current_goal)

@app.route('/goal/update', methods=['POST'])
def update_goal():
    goal_description = request.form.get('goal_description', '').strip()
    db = get_db()
    cursor = db.cursor()
    
    # Get current goal if exists
    current_goal = get_current_goal()
    
    if current_goal:
        # Update existing goal
        if goal_description:
            cursor.execute('''
                UPDATE goals
                SET description = ?
                WHERE id = ?
            ''', (goal_description, current_goal['id']))
    elif goal_description:
        # Create new goal
        target_date = (date.today() + timedelta(days=30)).isoformat()  # Default target date 30 days from now
        cursor.execute('''
            INSERT INTO goals (description, created_date, target_date, completed)
            VALUES (?, ?, ?, 0)
        ''', (goal_description, date.today().isoformat(), target_date))
    
    db.commit()
    flash('Goal updated successfully', 'success')
    
    # Return the updated view
    return view_goal()

@app.route('/goal/complete/<int:goal_id>', methods=['POST'])
def complete_goal(goal_id):
    db = get_db()
    cursor = db.cursor()
    
    # Mark the goal as completed
    cursor.execute('''
        UPDATE goals
        SET completed = 1, completion_date = ?
        WHERE id = ?
    ''', (date.today().isoformat(), goal_id))
    
    db.commit()
    flash('Goal marked as completed!', 'success')
    
    # Return the updated view
    return view_goal()


# ----- Notes Routes -----
@app.route('/notes/new')
def new_note():
    """Route to display the new note form."""
    return render_template('notes_editor.html')

@app.route('/notes/save', methods=['POST'])
def save_note():
    """Route to save a new note."""
    title = request.form.get('title')
    note_content = request.form.get('note')
    note_type = request.form.get('type', 'general')
    
    if not title or not note_content:
        flash('Title and note content are required!', 'error')
        return redirect(url_for('new_note'))
    
    db = get_db()
    today = date.today()
    
    db.execute(
        'INSERT INTO notes (title, note, type, created_date) VALUES (?, ?, ?, ?)',
        (title, note_content, note_type, today)
    )
    db.commit()
    
    flash('Note saved successfully!', 'success')
    return redirect(url_for('view_notes'))

@app.route('/notes/view')
def view_notes():
    """Route to view all notes."""
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
    
    return render_template('notes_list.html', notes=notes)

@app.route('/notes/<int:note_id>')
def view_note(note_id):
    """Route to view a specific note."""
    db = get_db()
    cursor = db.execute('SELECT id, title, note, type, created_date FROM notes WHERE id = ?', (note_id,))
    note = cursor.fetchone()
    
    if not note:
        flash('Note not found.', 'error')
        return redirect(url_for('view_notes'))
    
    note_dict = dict(note)
    
    # Format the date
    try:
        created_date_obj = datetime.strptime(note['created_date'], '%Y-%m-%d').date()
        note_dict['created_date'] = created_date_obj.strftime('%d %b %Y')
    except (ValueError, TypeError):
        note_dict['created_date'] = "Unknown Date"
    
    return render_template('note_view.html', note=note_dict)

@app.route('/notes/edit/<int:note_id>', methods=['GET', 'POST'])
def edit_note(note_id):
    """Route to edit a note."""
    db = get_db()
    
    if request.method == 'POST':
        title = request.form.get('title')
        note_content = request.form.get('note')
        note_type = request.form.get('type', 'general')
        
        if not title or not note_content:
            flash('Title and note content are required!', 'error')
            return redirect(url_for('edit_note', note_id=note_id))
        
        db.execute(
            'UPDATE notes SET title = ?, note = ?, type = ? WHERE id = ?',
            (title, note_content, note_type, note_id)
        )
        db.commit()
        
        flash('Note updated successfully!', 'success')
        return redirect(url_for('view_note', note_id=note_id))
    
    # GET request - show edit form
    cursor = db.execute('SELECT id, title, note, type, created_date FROM notes WHERE id = ?', (note_id,))
    note = cursor.fetchone()
    
    if not note:
        flash('Note not found.', 'error')
        return redirect(url_for('view_notes'))
    
    # Convert to dictionary for template
    note_dict = dict(note)
    
    return render_template('notes_editor.html', note=note_dict, edit_mode=True)

@app.route('/notes/delete/<int:note_id>')
def delete_note(note_id):
    """Route to delete a note."""
    db = get_db()
    
    # Check if the note exists
    cursor = db.execute('SELECT id FROM notes WHERE id = ?', (note_id,))
    note = cursor.fetchone()
    
    if not note:
        flash('Note not found.', 'error')
    else:
        # Delete the note
        db.execute('DELETE FROM notes WHERE id = ?', (note_id,))
        db.commit()
        flash('Note deleted successfully!', 'success')
    
    return redirect(url_for('view_notes'))

@app.route('/notes/delete/<int:note_id>', methods=['DELETE'])
def delete_note_htmx(note_id):
    """Route to handle HTMX delete requests for notes."""
    db = get_db()
    
    # Delete the note
    db.execute('DELETE FROM notes WHERE id = ?', (note_id,))
    db.commit()
    
    # No content response for HTMX delete
    return "", 204

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true' # <-- Change this line
    app.run(debug=debug_mode, port=5001) # debug=True for development
