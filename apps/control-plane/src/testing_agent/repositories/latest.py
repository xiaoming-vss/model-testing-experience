"""Select one newest row per resource without transferring its execution history."""

from sqlalchemy import func, select


def latest_per_resource(statement, resource_id, created_at, row_id):
    ranked = statement.add_columns(
        func.row_number()
        .over(
            partition_by=resource_id,
            order_by=(created_at.desc(), row_id.desc()),
        )
        .label("_latest_rank")
    ).subquery()
    return select(*(column for column in ranked.c if column.key != "_latest_rank")).where(
        ranked.c._latest_rank == 1
    )
