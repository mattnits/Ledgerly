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

## Goals page

The Goals page reuses the existing `savings_goals` table for one monthly
savings target per owner/month and `monthly_category_budgets` for category
limits. No existing table is renamed or rebuilt.

`init_db()` creates one additive table when it is missing:

- `long_term_savings_goals` stores the owner, name, `NUMERIC` target/current
  amounts, optional target date and notes, archive flag, and timestamps.

No manual SQL step is required. Back up `finance.db` while the application is
closed, then launch the updated app once; SQLAlchemy's `create_all()` creates
the new table without touching existing rows.

The same startup also adds partial unique indexes for monthly targets and
category budgets. These make the existing owner/month uniqueness rules fully
effective under SQLite's `NULL` handling; they do not rewrite either table.

## Transaction deduplication

`init_db()` performs an additive migration for transaction identity. It adds:

- `transactions.source_transaction_id VARCHAR(255) NULL`
- `transactions.dedupe_fingerprint VARCHAR(64) NULL`
- a non-unique lookup index on `dedupe_fingerprint`
- a partial unique index on `(account_id, source_transaction_id)` for active,
  non-deleted rows whose source ID is not null

Existing rows remain unchanged and receive `NULL` in both new columns. The
importer can still compare those rows by calculating their fallback fingerprint
in memory. No table is dropped or recreated and no existing transaction is
deleted. Back up `data/finance.db` while the application is closed, then launch
the updated app once; no manual SQL step is required.
