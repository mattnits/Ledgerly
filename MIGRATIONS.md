# Database migrations

The application runs additive SQLite migrations during `init_db()`; it does not
delete or recreate the database.

Before opening a real database with a new application version, make a normal
filesystem backup while the app is closed. On the next launch the app adds:

- `users.is_admin BOOLEAN NOT NULL DEFAULT 0`
- `categories.is_system BOOLEAN NOT NULL DEFAULT 0`
- `categories.created_by_user_id VARCHAR(36) NULL`

If existing users have no Admin, the earliest user by `created_at`, then `id`,
becomes the sole Admin. Existing default categories become system categories.
Legacy custom categories remain unowned because their creator cannot be inferred
safely. New custom categories record the current user's ID.
