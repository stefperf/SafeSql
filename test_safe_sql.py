# test_safe_sql_builders.py
import pytest
from itertools import chain


from safe_sql import (
    SafeSql,
    SafeSqlParam,
    SafeSqlInt,
    SafeSqlLikePattern,
    SafeSqlWildcard,
    SafeSqlWhitelisted,
    SafeSqlUpsertRows,
)


# -----------------------------
# SafeSqlParam
# -----------------------------
def test_safe_sql_param_build():
    p = SafeSqlParam(42)
    sql, params = p.build()
    assert sql == "?"
    assert params == [42]


# -----------------------------
# SafeSqlInt
# -----------------------------
def test_safe_sql_int_build():
    i = SafeSqlInt(10)
    sql, params = i.build()
    assert sql == "10"
    assert params == []

    with pytest.raises(TypeError):
        SafeSqlInt("not-an-int")  # type: ignore


# -----------------------------
# SafeSqlLikePattern
# -----------------------------
def test_safe_sql_like_pattern_escape():
    pattern = SafeSqlLikePattern("100%", SafeSqlWildcard.UNDERSCORE, "foo[bar")
    sql, params = pattern.build()
    # Escapes %, _, and [
    assert sql.startswith("? ESCAPE '['")
    assert params[0] == "100[%_foo[[bar"


def test_safe_sql_like_pattern_no_escape():
    pattern = SafeSqlLikePattern("abc", SafeSqlWildcard.PERCENT)
    sql, params = pattern.build()
    # Only explicit wildcard % is included
    assert sql == "?"
    assert params[0] == "abc%"


def test_safe_sql_like_pattern_invalid_type():
    with pytest.raises(TypeError):
        SafeSqlLikePattern("abc", 123)  # type: ignore


# -----------------------------
# SafeSqlWhitelisted
# -----------------------------
def test_safe_sql_whitelisted_valid():
    w = SafeSqlWhitelisted("users", ("users", "orders"))
    sql, params = w.build()
    assert sql == "users"
    assert params == []


def test_safe_sql_whitelisted_invalid():
    with pytest.raises(ValueError):
        SafeSqlWhitelisted("invalid", ["users", "orders"])


def test_safe_sql_whitelisted_invalid_types():
    with pytest.raises(TypeError):
        SafeSqlWhitelisted(123, ("users",))  # type: ignore
    with pytest.raises(TypeError):
        SafeSqlWhitelisted("users", "not-a-sequence")


# -----------------------------
# SafeSql
# -----------------------------
def test_safe_sql_combine_snippets():
    where1 = SafeSql(
        "WHERE user_id >",
        SafeSqlParam(42),
    )
    s = SafeSql(
        "SELECT TOP ", SafeSqlInt(1), "*",
        "FROM", SafeSqlWhitelisted("users", ("admins", "users")),
        where1,
        "AND name LIKE", SafeSqlLikePattern("Stefan", SafeSqlWildcard.PERCENT),
    )
    sql, params = s.build()
    assert sql == "SELECT TOP 1 * FROM users WHERE user_id > ? AND name LIKE ?"
    assert params == [42, "Stefan%"]


def test_safe_sql_invalid_type():
    with pytest.raises(TypeError):
        SafeSql("SELECT", 123)  # type: ignore


# -----------------------------
# SafeSqlUpsertRows
# -----------------------------
def test_safe_sql_upsert_rows_build():
    table = "my_table"
    col1 = "id1"
    col2 = "id2"
    col3 = "v1"
    col4 = "v2"
    rows = [
        (1, 10, "a1", "a2"),
        (2, 20, "b1", "b2"),
    ]

    right_sql = """
MERGE INTO my_table WITH (HOLDLOCK) AS target
USING (
    VALUES
        (?,?,?,?),(?,?,?,?)
) AS source (id1,id2,v1,v2)
    ON target.id1 = source.id1 AND target.id2 = source.id2
WHEN MATCHED THEN
    UPDATE SET 
        target.v1 = source.v1, target.v2 = source.v2
WHEN NOT MATCHED BY TARGET THEN
    INSERT (id1,id2,v1,v2)
    VALUES (source.id1,source.id2,source.v1,source.v2);
"""

    upsert = SafeSqlUpsertRows(
        target_table=table,
        on_columns=[col1, col2],
        columns=[col1, col2, col3, col4],
        rows=rows
    )

    sql, params = upsert.build()
    assert sql == right_sql
    assert params == list(chain.from_iterable(rows))

    row_dicts = [
        dict(id1=1, id2=10, v1="a1", v2="a2"),
        dict(id1=2, id2=20, v1="b1", v2="b2"),
    ]
    upsert1 = SafeSqlUpsertRows.from_row_dicts(
        target_table=table,
        on_columns=[col1, col2],
        row_dicts=row_dicts
    )
    sql1, params1 = upsert1.build()
    assert sql1 == right_sql
    assert params1 == list(chain.from_iterable(rows))


def test_safe_sql_upsert_rows_invalid_rows_length():
    table = "my_table"
    col1 = "id"
    col2 = "value"
    # Row lengths mismatch
    rows = [
        (1, "a"),
        (2,)
    ]

    with pytest.raises(ValueError):
        SafeSqlUpsertRows(
            target_table=table,
            columns=[col1, col2],
            on_columns=[col1],
            rows=rows
        )


def test_safe_sql_upsert_rows_empty_rows():
    table = "my_table"
    col1 = "id"
    col2 = "value"
    with pytest.raises(ValueError):
        SafeSqlUpsertRows(
            target_table=table,
            columns=[col1, col2],
            on_columns=[col1],
            rows=[]
        )


def test_safe_sql_upsert_rows_on_columns_not_subset():
    table = "my_table"
    col1 = "id"
    col2 = "value"
    col3 = "extra"
    rows = [
        (1, "a"),
        (2, "b")
    ]

    with pytest.raises(ValueError):
        SafeSqlUpsertRows(
            target_table=table,
            columns=[col1, col2],
            on_columns=[col3],
            rows=rows
        )
