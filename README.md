# Melga - Task Management App

A simple task management web application built with Flask and HTMX.

---

## Features

- Create, update, and delete tasks
- Mark tasks as completed
- Set due dates for tasks
- Track history of task actions
- Snooze tasks to later dates
- Send notifications for task reminders

---

## Technology Stack

- Backend: Flask (Python)
- Frontend: HTML, CSS, JavaScript with HTMX
- Database: SQLite
- UI Framework: Pico CSS

---

## Prerequisites

Before you begin, ensure you have the following installed:
- Python 3.x
- pip (Python package installer)

---

## Local Development Setup

Follow these steps to get your local development environment running:

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd Melga
    ```
    *(Replace `<your-repository-url>` with the actual URL)*

2.  **(Optional but Recommended) Create and activate a virtual environment:**
    ```bash
    # Windows
    python -m venv venv
    .\venv\Scripts\activate

    # macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Initialize the database:**
    This command sets up the initial database schema.
    ```bash
    flask init-db
    ```

5.  **Run the application:**
    Use `flask run` for development. It provides features like debugging and automatic reloading on code changes.
    ```bash
    flask run
    ```
    The application will typically be available at `http://127.0.0.1:5000/`.

    Alternatively, you can use:
    ```bash
    python app.py
    ```
    This directly runs the Python script but might not offer the same development conveniences as `flask run`.