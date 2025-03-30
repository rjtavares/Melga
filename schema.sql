DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS task_actions;

CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    due_date DATE NOT NULL,
    completed BOOLEAN NOT NULL DEFAULT 0 -- 0 for false, 1 for true
);

CREATE TABLE task_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    action_description TEXT NOT NULL,
    action_date DATE NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);