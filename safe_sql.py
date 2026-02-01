# Utilities for preventing SQL injection in dynamically composed SQL statements executed on SqlServer via pyodbc.
#
from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import Enum
from itertools import chain
from typing import Any, ClassVar, Union

from pydantic import BaseModel, model_validator


# alias informing the developers that they are responsible for the safety of a string
DeveloperCheckedStr = str


class SafeSqlBuilder(ABC):
    PYODBC_PARAM_PLACEHOLDER: ClassVar[str] = "?"
    MSSQL_MAX_PARAMS: ClassVar[int] = 2100

    def build(self) -> tuple[str, list[Any]]:
        sql, params = self._build()
        if len(params) > self.MSSQL_MAX_PARAMS:
            raise ValueError("SqlServer max. nr. of parameters exceeded")
        return sql, params

    @abstractmethod
    def _build(self) -> tuple[str, list[Any]]:
        """return a SQL snippet possibly containing pyodbc positional parameter placeholders and a list of parameter"""
        pass


class SafeSql(SafeSqlBuilder):
    """
    Class for combining multiple SQL snippets into a SQL snippet
    invulnerable to SQL injection.
    """

    def __init__(self, *parts: Union[SafeSqlBuilder, DeveloperCheckedStr]):
        # Validate that snippets is a sequence
        if not isinstance(parts, Sequence):
            raise TypeError(f"snippets must be a Sequence, got {type(parts).__name__}")

        # Validate each element
        for i, part in enumerate(parts):
            if not isinstance(part, (SafeSqlBuilder, DeveloperCheckedStr)):
                raise TypeError(
                    f"Each snippet must be SafeSqlBuilder or DeveloperCheckedStr, "
                    f"but element {i} is {type(part).__name__}"
                )

        self.parts = parts

    def _build(self) -> tuple[str, list[Any]]:
        def safely_concatenate(left: str, right: str) -> str:
            """ensure consecutive sql snippets are separated by one space"""
            if not left:
                return right.strip()
            return left + ' ' + right.strip()

        sql: str = ""
        params: list[Any] = []
        for part in self.parts:
            if isinstance(part, SafeSqlBuilder):
                added_sql, added_params = part._build()
            else:  # if isinstance(part, str):
                added_sql, added_params = part, []
            sql = safely_concatenate(sql, added_sql)
            params += added_params

        return sql, params


class SafeSqlWildcard(Enum):
    """intentional SQL wildcard"""
    PERCENT = '%'
    UNDERSCORE = '_'


class SafeSqlLikePattern(SafeSqlBuilder):
    """
    Class producing a safe Sql LIKE pattern.
    Wildcards must be given explicitly with the Wildcard inner class.
    Any wildcard not given explicitly is escaped to prevent context injection.
    """
    ESCAPE_CHAR: ClassVar[str] = '['

    def __init__(self, *parts: Union[str, 'SafeSqlWildcard']):
        # Validate that we received a sequence of arguments
        if not parts:
            raise TypeError("At least one part must be provided")

        # Validate each element
        for i, part in enumerate(parts):
            if not isinstance(part, (str, SafeSqlWildcard)):
                raise TypeError(
                    f"Each part must be str or SafeSqlWildcard, "
                    f"but element {i} is {type(part).__name__}"
                )

        self.parts = parts

    def _build(self) -> tuple[str, list[Any]]:

        def process_part(p: Union[str, SafeSqlWildcard]) -> tuple[str, bool]:
            """get the corresponding safe string and True or False depending on whether any escapes were executed"""
            # escaping unexpected wildcards protects from context injection
            if isinstance(p, str):
                escaped = ""
                executed_escapes = False
                for ch in p:
                    if ch in (self.ESCAPE_CHAR, '%', '_'):
                        escaped += self.ESCAPE_CHAR + ch
                        executed_escapes = True
                    else:
                        escaped += ch
                return escaped, executed_escapes
            else:  # if isinstance(p, SqlWildcard):
                return p.value, False

        any_escape_needed = False
        param = ""
        for part in self.parts:
            string, escape_needed = process_part(part)
            param += string
            any_escape_needed = any_escape_needed or escape_needed

        escape_clause_if_needed = f" ESCAPE '{SafeSqlLikePattern.ESCAPE_CHAR}'" if any_escape_needed else ""
        return self.PYODBC_PARAM_PLACEHOLDER + escape_clause_if_needed, [param]


class SafeSqlInt(SafeSqlBuilder):
    """class ensuring that the given value is an int; useful for sanitizing TOP n directives"""
    def __init__(self, value: int) -> None:
        if not isinstance(value, int):
            raise TypeError(f"value must be int, got {type(value).__name__}")
        self.value: int = value

    def _build(self) -> tuple[str, list[Any]]:
        return str(self.value), []


class SafeSqlParam(SafeSqlBuilder):
    """class handling a SQL parameter of any type"""
    def __init__(self, value: Any) -> None:
        self.value: Any = value

    def _build(self) -> tuple[str, list[Any]]:
        return self.PYODBC_PARAM_PLACEHOLDER, [self.value]


class SafeSqlWhitelisted(SafeSqlBuilder):
    """class allowing only a string chosen from a whitelist; use it for dynamically choosing a SQL object name"""
    def __init__(self, string: str, whitelist: Sequence[str]):
        if not isinstance(string, str):
            raise TypeError(f"string must be str, got {type(string).__name__}")
        if isinstance(whitelist, str) or not isinstance(whitelist, Sequence):
            raise TypeError(f"whitelist must be a Sequence[str], got {type(whitelist).__name__}")
        if not all(isinstance(item, str) for item in whitelist):
            raise TypeError("all elements of whitelist must be str")

        if string not in whitelist:
            raise ValueError(f"string '{string}' not in whitelist {whitelist}")

        self.string = string
        self.whitelist = frozenset(whitelist)

    def _build(self) -> tuple[str, list[Any]]:
        return self.string, []


class SafeSqlUpsertRows(SafeSqlBuilder, BaseModel):
    """
    Class for building an upsert command sanitizing all values but no SQL names.
    It is the developer's responsibility to ensure that target_table and column names are safe strings!
    """
    target_table: DeveloperCheckedStr
    on_columns: Sequence[DeveloperCheckedStr]
    columns: Sequence[DeveloperCheckedStr]
    rows: Sequence[Sequence[Any]]

    @model_validator(mode="after")
    def validate_inputs(self):
        # Check rows exist
        if not self.rows:
            raise ValueError("rows must not be empty")

        # Check all rows have same non-zero length
        row_lengths = {len(r) for r in self.rows}
        row_length = list(row_lengths)[0]
        if len(row_lengths) != 1 or row_length == 0:
            raise ValueError("all rows must have the same non-zero length")

        # Check consistency between row length and columns length
        if row_length != len(self.columns):
            raise ValueError("each row must have the same length as columns")

        # Check there are no repeated on_columns
        if len(set(self.on_columns)) < len(self.on_columns):
            raise ValueError("columns should contain no repetitions")

        # Check there are no repeated columns
        if len(set(self.columns)) < len(self.columns):
            raise ValueError("columns should contain no repetitions")

        # Check on_columns are contained in columns
        if not set(self.on_columns).issubset(self.columns):
            raise ValueError("on_columns must be a subset of columns")

        return self

    @staticmethod
    def from_row_dicts(
        target_table: DeveloperCheckedStr,
        on_columns: Sequence[DeveloperCheckedStr],
        row_dicts: Sequence[dict[DeveloperCheckedStr, Sequence[Any]]],
    ) -> 'SafeSqlUpsertRows':
        columns: list[DeveloperCheckedStr] = list(row_dicts[0].keys()) if row_dicts else []
        rows: list[list[Any]] = [list(rd.values()) for rd in row_dicts]
        return SafeSqlUpsertRows(
            target_table=target_table, on_columns=on_columns, columns=columns, rows=rows
        )

    def _build(self) -> tuple[str, list[Any]]:
        update_columns: list[str] = [c for c in self.columns if c not in self.on_columns]

        value_row: str = "(" + ",".join(self.PYODBC_PARAM_PLACEHOLDER for _ in range(len(self.columns))) + ")"
        value_rows: str = ",".join(value_row for _ in range(len(self.rows)))

        column_list: str = ",".join(c for c in self.columns)

        on_condition = " AND ".join(f"target.{c} = source.{c}" for c in self.on_columns)

        update_command = ", ".join(f"target.{c} = source.{c}" for c in update_columns)

        insert_column_list = ",".join(f"source.{c}" for c in self.columns)

        sql = f"""
MERGE INTO {self.target_table} WITH (HOLDLOCK) AS target
USING (
    VALUES
        {value_rows}
) AS source ({column_list})
    ON {on_condition}
WHEN MATCHED THEN
    UPDATE SET 
        {update_command}
WHEN NOT MATCHED BY TARGET THEN
    INSERT ({column_list})
    VALUES ({insert_column_list});
"""

        params: list[Any] = list(chain.from_iterable(self.rows))

        return sql, params
