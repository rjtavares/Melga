from flask import Flask, render_template, request, g, make_response, get_flashed_messages, flash, json, redirect, url_for
from datetime import date, datetime, timedelta
import notifications  # Import the entire module instead of specific function
from db import *
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
    
    # Get the highest priority task
    priority_task = get_priority_task()

    return render_template('index.html', tasks=tasks, today=today, activity_data=last_21_days, 
                           current_goal=current_goal, priority_task=priority_task)


# --- HTMX Routes ---

def make_task_list():
    """Endpoint to fetch the task list partial for HTMX updates."""
    tasks = get_tasks()
    current_goal = get_current_goal()
    response = make_response(render_template('_tasks.html', tasks=tasks, current_goal=current_goal))
    response.headers['HX-Trigger'] = 'showFlash'
    return response

@app.route('/add', methods=['POST'])
def add_task():
    description = request.form['description']
    due_date_str_input = request.form['due_date'] # Input is YYYY-MM-DD from HTML date input
    link_to_goal = request.form.get('link_goal')

    # Parse the input date using our utility function
    due_date_obj = parse_date(due_date_str_input)
    if not due_date_obj:
        flash('Invalid date format.', 'error')
        return make_task_list() # Return updated list to show flash

    goal_id = None
    if link_to_goal:
        current_goal = get_current_goal()
        if current_goal:
            goal_id = current_goal['id']
    
    insert_task(description, due_date_obj, goal_id)
    flash('Task added successfully!', 'success')

    # Return the updated task list partial for HTMX
    return make_task_list()



@app.route('/toggle/<int:task_id>', methods=['POST'])
def toggle_task(task_id):
    task = get_task(task_id)
    if task:
        new_status = not task['completed']
        today = date.today()
        
        if new_status:  # If task is being marked as completed
            update_task(task_id, {'completed': new_status, 'completion_date': get_db_date(today)})
        else:  # If task is being marked as pending
            update_task(task_id, {'completed': new_status, 'completion_date': None})
        
        status_text = "completed" if new_status else "marked as pending"
        flash(f'Task {status_text}.', 'success')
    else:
        flash('Task not found.', 'error')

    # Get the updated list of tasks and priority task for the response
    tasks = get_tasks()
    current_goal = get_current_goal()
    priority_task = get_priority_task()
    
    # Create response with both task list and HX-Trigger for goal refresh
    response = make_response(render_template('_tasks.html', tasks=tasks, current_goal=current_goal))
    response.headers['HX-Trigger'] = json.dumps({
        'showFlash': True,
        'refreshGoalSection': {'priority_task': priority_task is not None},
        'refreshPriorityTask': True
    })
    
    return response


@app.route('/delete/<int:task_id>', methods=['DELETE'])
def remove_task(task_id):
    delete_task(task_id)
    flash('Task deleted.', 'info')

    # Return the updated task list partial for HTMX
    return make_task_list()


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
    return make_task_list()


# --- Task History Routes ---

@app.route('/task/<int:task_id>')
def task_history(task_id):
    """Show task history page with all actions for a specific task."""
    task = get_task(task_id)

    if not task:
        return redirect(url_for('index'))

    actions = get_actions(task_id)

    # Render the task history template with task details and actions
    return render_template('task_history.html', task=task, actions=actions)


@app.route('/task/<int:task_id>/next_action', methods=['POST'])
def update_next_action(task_id):
    """Update the next_action for a specific task."""
    next_action_text = request.form.get('next_action', '').strip()
    try:
        update_task(task_id, {'next_action': next_action_text})
        # Fetch the updated task data to pass to the partial
        updated_task = get_task(task_id)
        if updated_task:
             # Return the VIEW partial to replace the edit form after saving
             return render_template('_next_action_view.html', task=dict(updated_task))
        else:
             # Handle case where task might have been deleted in the meantime
             return "Task not found", 404
    except Exception as e:
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
        return render_template('_next_action_edit.html', task=task)
    else:
        # Optionally return an error snippet or handle appropriately
        return "Task not found", 404


@app.route('/task/<int:task_id>/view_next_action', methods=['GET'])
def get_view_next_action(task_id):
    """Serve the partial template for viewing next_action."""
    task = get_task(task_id)
    if task:
        return render_template('_next_action_view.html', task=task)
    else:
        return "Task not found", 404


@app.route('/task/<int:task_id>/add-action', methods=['POST'])
def add_task_action(task_id):
    """Add a new action to a task and optionally snooze the task."""
    action_description = request.form.get('action_description')
    action_snooze = request.form.get('action_snooze')
    
    if not action_description:
        flash('Action description is required!', 'error')
        return '', 400
    
    task = get_task(task_id)

    if not task:
        flash('Task not found.', 'error')
        return '', 404
    
    # Add the action
    today = get_db_date()
    insert_action(task_id, action_description, today)
    
    # Handle snoozing if action_snooze is provided
    if action_snooze:
        message, status = snooze_task(task_id, int(action_snooze))
        flash(message, status)

    actions = get_actions(task_id)
    
    # Return the updated actions list and summary (swap-oob)
    actions_html = render_template('_actions.html', actions=actions)
    summary_html = render_template('_task_summary.html', task=get_task(task_id))
    # Wrap summary_html in a div with id and hx-swap-oob
    summary_oob = f'<div id="task-summary-container" hx-swap-oob="true">{summary_html}</div>'
    response_html = actions_html + summary_oob
    response = make_response(response_html)
    response.headers['HX-Trigger'] = json.dumps({'showFlash': True})
    return response


@app.route('/snooze-modal/<int:task_id>/<int:days>', methods=['GET'])
def snooze_modal(task_id, days):
    """Show a modal dialog to enter action before snoozing a task."""
    # Validate days input
    if days not in [1, 3, 7, 30]:
        flash('Invalid snooze duration.', 'error')
        return '', 400
    
    # Format text for display
    day_str = "day" if days == 1 else "days"
    days_text = f"{days} {day_str}"
    if days == 7:
        days_text += " (1 week)"
    elif days == 30:
        days_text += " (1 month)"
    
    return render_template('_snooze_modal.html', task_id=task_id, days=days, days_text=days_text)


@app.route('/snooze/<int:task_id>/<int:days>', methods=['POST'])
def snooze_task(task_id, days):
    """Snooze a task, add an action entry, and optionally update next action."""
    action_description = request.form.get('action_description')
    next_action_text = request.form.get('next_action', '').strip() # Get optional next action
    
    # Don't allow snoozing without an action description
    if not action_description:
        flash('Action description is required to snooze a task.', 'error')
        return make_task_list()
    
    task = get_task(task_id)

    if task:
        message, status = snooze_task(task_id, days)
        flash(message, status)

        if status == 'success':
            # Update next action if provided
            if next_action_text:
                update_task(task_id, {'next_action': next_action_text})

            # Add an action entry for the snooze
            today = get_db_date()        
            insert_action(task_id, action_description, today)
            flash('Action added successfully.', 'success')
        
    else:
        flash('Task not found.', 'error')

    # Return the updated task list partial for HTMX
    return make_task_list()

def snooze_task(task_id, days):
    task = get_task(task_id)
    if days not in [1, 3, 7, 30]:
        return False, 'Invalid snooze duration.'
    current_due_date = date.today()
    if task['due_date']:
        # Use our parse_date utility to safely parse the date
        parsed_date = parse_date(task['due_date'])
        if parsed_date:
            current_due_date = parsed_date
            
    # Add days to the current due date
    new_due_date = current_due_date + timedelta(days=days)

    # Determine day string for flash message
    day_str = "day" if days == 1 else "days"
    week_str = " (1 week)" if days == 7 else ""
    month_str = " (1 month)" if days == 30 else ""
    formatted_due_date = format_date(new_due_date, DATE_DISPLAY_FORMAT)

    # Update the task with the new due date using our standardized format
    update_task(task_id, {'due_date': get_db_date(new_due_date)})
    return True, f'Task snoozed for {days} {day_str}{week_str}{month_str} until {formatted_due_date}.'



@app.route('/flash-messages')
def get_flash_messages():
    """Endpoint to fetch flash messages for HTMX updates."""
    messages = get_flashed_messages(with_categories=True)
    messages_dicts = [{"category": category, "message": message} for category, message in messages]
    return render_template('_flash_messages.html', messages=messages_dicts)


@app.route('/task/action/<int:action_id>/delete', methods=['DELETE'])
def remove_action(action_id):
    """Delete a specific action from a task."""
    
    action = get_action(action_id)
    
    if not action:
        return render_template('_actions.html', actions=[]), 404
    
    task_id = action['task_id']
    delete_action(action_id)
    actions = get_actions(task_id)
    
    # Return the updated actions list partial
    return render_template('_actions.html', actions=actions)


@app.route('/reset-date/<int:task_id>', methods=['POST'])
def reset_date(task_id):
    """Reset the due date of a task to today."""
    task = get_task(task_id)

    if task:
        # Check if task is overdue
        today = date.today()
        
        # Update the task with today's date
        today_db_format = get_db_date(today)
        update_task(task_id, {'due_date': today_db_format})
        
        # Add an action entry for resetting the date
        insert_action(task_id, "Reset due date to today", today)
        
        formatted_date = format_date(today)
        flash(f'Due date for task reset to today ({formatted_date}).', 'success')
    else:
        flash('Task not found.', 'error')

    # Return the updated task list partial for HTMX
    return make_task_list()


@app.route('/goal/edit')
def edit_goal():
    current_goal = get_current_goal()
    return render_template('_goal_edit.html', current_goal=current_goal)

@app.route('/goal/view')
def view_goal():
    current_goal = get_current_goal()
    priority_task = get_priority_task()
    return render_template('_goal_view.html', current_goal=current_goal, priority_task=priority_task)

@app.route('/priority-task')
def get_priority_task_container():
    """Return the priority task container HTML for HTMX updates."""
    priority_task = get_priority_task()
    return render_template('_priority_task.html', priority_task=priority_task)

@app.route('/goal/update', methods=['POST'])
def update_goal():
    goal_description = request.form.get('goal_description', '').strip()

    # Get current goal if exists
    current_goal = get_current_goal()
    
    if current_goal:
        # Update existing goal
        if goal_description:
            update_goal(current_goal['id'], {'description': goal_description})
    elif goal_description:
        # Create new goal
        today = date.today()
        # Default target date 30 days from now
        target_date = today + timedelta(days=30)
        insert_goal(goal_description, today, target_date)
    
    flash('Goal updated successfully', 'success')
    
    # Return the updated view
    return view_goal()

@app.route('/goal/complete/<int:goal_id>', methods=['POST'])
def complete_goal(goal_id):
    # Mark the goal as completed
    update_goal(goal_id, {'completed': 1, 'completion_date': get_db_date(date.today())})
    
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
    
    today = date.today()
    
    insert_note(title, note_content, note_type, today)
    
    flash('Note saved successfully!', 'success')
    return redirect(url_for('view_notes'))

@app.route('/notes/view')
def view_notes():
    """Route to view all notes."""
    notes = get_notes()    
    return render_template('notes_list.html', notes=notes)

@app.route('/notes/<int:note_id>')
def view_note(note_id):
    """Route to view a specific note."""
    note = get_note(note_id)
    
    if not note:
        flash('Note not found.', 'error')
        return redirect(url_for('view_notes'))
        
    # Format the date using our utility function
    note['created_date'] = get_display_date(note['created_date'], short=True)
    
    return render_template('note_view.html', note=note)

@app.route('/notes/edit/<int:note_id>', methods=['GET', 'POST'])
def edit_note(note_id):
    """Route to edit a note."""
    
    if request.method == 'POST':
        title = request.form.get('title')
        note_content = request.form.get('note')
        note_type = request.form.get('type', 'general')
        
        if not title or not note_content:
            flash('Title and note content are required!', 'error')
            return redirect(url_for('edit_note', note_id=note_id))
        
        update_note(note_id, {'title': title, 'note': note_content, 'type': note_type})
        
        flash('Note updated successfully!', 'success')
        return redirect(url_for('view_note', note_id=note_id))
    
    # GET request - show edit form
    note = get_note(note_id)
    
    if not note:
        flash('Note not found.', 'error')
        return redirect(url_for('view_notes'))
    
    return render_template('notes_editor.html', note=note, edit_mode=True)

@app.route('/notes/delete/<int:note_id>')
def remove_note(note_id):
    """Route to delete a note."""
    
    # Check if the note exists
    note = get_note(note_id)
    
    if not note:
        flash('Note not found.', 'error')
    else:
        delete_note(note_id)
        flash('Note deleted successfully!', 'success')
    
    return redirect(url_for('view_notes'))

@app.route('/notes/delete/<int:note_id>', methods=['DELETE'])
def delete_note_htmx(note_id):
    """Route to handle HTMX delete requests for notes."""
    delete_note(note_id)
    
    # No content response for HTMX delete
    return "", 204

@app.route('/task/<int:task_id>/toggle-priority', methods=['POST'])
def toggle_task_priority(task_id):
    """Toggle the priority of a task between 0 (not priority) and 1 (high priority)."""
    task = get_task(task_id)
    
    if not task:
        flash('Task not found.', 'error')
        return "", 404
    
    # Get current priority value, default to 0 if None
    current_priority = task.get('priority', 0) or 0
    
    # Toggle the priority value (0 -> 1, 1 -> 0)
    new_priority = 0 if current_priority else 1
    
    # Update the task
    update_task(task_id, {'priority': new_priority})
    
    priority_text = "high priority" if new_priority else "normal priority"
    flash(f'Task marked as {priority_text}.', 'success')
    
    # Get updated actions for the task
    actions = get_actions(task_id)
    task = get_task(task_id)
    
    # Format dates and check overdue status
    due_date = parse_date(task['due_date'])
    task['due_date_display'] = format_date(due_date)
    task['is_overdue'] = due_date < date.today() and not task['completed']
    
    # Set the response headers to trigger flash display and refresh key elements
    response = make_response(render_template('_task_actions.html', actions=actions, task=task))
    response.headers['HX-Trigger'] = json.dumps({
        'showFlash': True,
        'refreshTaskDetails': {'task_id': task_id, 'priority': new_priority}
    })
    
    return response

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true' # <-- Change this line
    app.run(debug=debug_mode, port=5001) # debug=True for development
