"""Database-specific transaction preparation for portable savepoints."""


def ensure_outer_transaction(session) -> None:
    """Ensure SQLite does not commit an outer transaction when releasing a savepoint."""
    connection = session.connection()
    if (
        connection.dialect.name == "sqlite"
        and not connection.connection.driver_connection.in_transaction
    ):
        connection.exec_driver_sql("BEGIN")
