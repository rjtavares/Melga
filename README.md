# Melga - Task Management App

A simple task management web application built with Flask and HTMX.

## Features

- Create, update, and delete tasks
- Mark tasks as completed
- Set due dates for tasks
- Track history of task actions
- Snooze tasks to later dates
- Send notifications for task reminders

## Technology Stack

- Backend: Flask (Python)
- Frontend: HTML, CSS, JavaScript with HTMX
- Database: SQLite
- UI Framework: Pico CSS

## Local Development

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Initialize the database:
   ```
   flask init-db
   ```
4. Run the application:
   ```
   flask run
   ```
   or
   ```
   python app.py
   ```

## Deployment

This application is configured for deployment on platforms like Heroku, Render, or PythonAnywhere.

- The `Procfile` specifies how to run the app using Gunicorn
- `requirements.txt` lists all dependencies
- `runtime.txt` specifies the Python version
