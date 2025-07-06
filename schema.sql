DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS task_actions;
DROP TABLE IF EXISTS goals;
DROP TABLE IF EXISTS notes;
DROP TABLE IF EXISTS random_things_to_do;
DROP TABLE IF EXISTS habits;

CREATE TABLE goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        description TEXT NOT NULL,
        created_date DATE NOT NULL,
        target_date DATE NOT NULL,
        completed BOOLEAN NOT NULL DEFAULT 0, -- 0 for false, 1 for true
        completion_date DATE
);

CREATE TABLE habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    created_date DATE NOT NULL,
    periodicity TEXT NOT NULL -- e.g., 'weekly', 'biweekly', 'monthly', 'quarterly', 'yearly'
);

CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    due_date DATE NOT NULL,
    completed BOOLEAN NOT NULL DEFAULT 0, -- 0 for false, 1 for true
    last_notification DATE,
    completion_date DATE,
    next_action TEXT,
    goal_id INTEGER,
    priority INTEGER,
    give_up BOOLEAN NOT NULL DEFAULT 0, -- 0 for false, 1 for true
    created_date DATE NOT NULL,
    habit_id INTEGER,
    FOREIGN KEY (goal_id) REFERENCES goals(id),
    FOREIGN KEY (habit_id) REFERENCES habits(id)
);

CREATE TABLE task_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    action_description TEXT NOT NULL,
    action_date DATE NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    note TEXT NOT NULL,
    type TEXT,
    created_date DATE NOT NULL
);

CREATE TABLE random_things_to_do (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    completed BOOLEAN NOT NULL DEFAULT 0, -- 0 for false, 1 for true
    completion_date DATE,
    link TEXT
);