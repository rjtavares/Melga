DROP TABLE IF EXISTS tasks;

CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT NOT NULL,
    due_date DATE NOT NULL,
    completed BOOLEAN NOT NULL DEFAULT 0 -- 0 for false, 1 for true
);
