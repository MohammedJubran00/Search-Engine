"""SQLAlchemy engine and session factory for PostgreSQL.

Routes and repositories import `get_db` from `database.py`. No tables are
created here; Alembic owns schema changes.
"""
