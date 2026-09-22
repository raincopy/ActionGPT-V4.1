from __future__ import annotations

import base64
import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from .config import DB_CONNECTIONS_CFG, POSTGRES_DEFAULTS
from .db_connection_config import DbConnectionConfig


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


class DbService:
    def __init__(self, defaults: dict[str, Any] | None = None) -> None:
        self.defaults = dict(defaults or POSTGRES_DEFAULTS)
        self.connections = DbConnectionConfig(DB_CONNECTIONS_CFG, self.defaults)

    def selected_connection_id(self, target: dict[str, Any]) -> str:
        return self.connections.default_id

    def list_tables(self, target: dict[str, Any]) -> dict[str, Any]:
        schema = str(target.get("schema") or "public")
        rows = self._query(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY table_name
            """,
            [schema],
            target,
        )
        return {"schema": schema, "tables": rows, "count": len(rows)}

    def list_columns(self, target: dict[str, Any]) -> dict[str, Any]:
        schema = str(target.get("schema") or "public")
        table = self._required(target, "table")
        rows = self._query(
            """
            SELECT column_name, data_type, udt_name, is_nullable,
                   column_default, ordinal_position, character_maximum_length,
                   numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            [schema, table],
            target,
        )
        return {"schema": schema, "table": table, "columns": rows, "count": len(rows)}

    def read_data(self, target: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
        schema = str(target.get("schema") or "public")
        table = self._required(target, "table")
        columns = options.get("columns") or ["*"]
        conditions = options.get("conditions") or {}
        order_by = options.get("order_by") or []
        limit = max(1, min(int(options.get("limit", 100)), 10000))

        table_sql = f"{self._quote_identifier(schema)}.{self._quote_identifier(table)}"
        if columns == ["*"] or columns == "*":
            column_sql = "*"
        else:
            if not isinstance(columns, list) or not columns:
                raise ValueError("columns는 컬럼명 목록 또는 '*'이어야 한다")
            column_sql = ", ".join(self._quote_identifier(str(column)) for column in columns)

        params: list[Any] = []
        where_parts: list[str] = []
        if not isinstance(conditions, dict):
            raise ValueError("conditions는 {컬럼명: 값} 형식이어야 한다")
        for column, value in conditions.items():
            identifier = self._quote_identifier(str(column))
            if value is None:
                where_parts.append(f"{identifier} IS NULL")
            else:
                where_parts.append(f"{identifier} = %s")
                params.append(value)

        query = f"SELECT {column_sql} FROM {table_sql}"
        if where_parts:
            query += " WHERE " + " AND ".join(where_parts)
        if order_by:
            if isinstance(order_by, str):
                order_by = [order_by]
            order_parts = []
            for item in order_by:
                pieces = str(item).strip().split()
                column = self._quote_identifier(pieces[0])
                direction = pieces[1].upper() if len(pieces) > 1 else "ASC"
                if direction not in {"ASC", "DESC"}:
                    raise ValueError(f"허용되지 않은 정렬 방향이다: {direction}")
                order_parts.append(f"{column} {direction}")
            query += " ORDER BY " + ", ".join(order_parts)
        query += " LIMIT %s"
        params.append(limit)
        rows = self._query(query, params, target)
        return {"schema": schema, "table": table, "rows": rows, "count": len(rows), "limit": limit}

    def execute_select(self, sql_text: str, target: dict[str, Any]) -> dict[str, Any]:
        if not sql_text.strip():
            raise ValueError("실행할 SELECT SQL이 없다")
        try:
            rows = self._query(sql_text, [], target, allow_multi=False)
        except Exception as exc:
            missing = self._missing_result(exc)
            if missing is not None:
                return missing
            raise
        return {"rows": rows, "count": len(rows)}

    def execute_ddl(self, sql_text: str, target: dict[str, Any]) -> dict[str, Any]:
        return self._execute_change(sql_text, target, operation="DDL")

    def execute_dml(self, sql_text: str, target: dict[str, Any]) -> dict[str, Any]:
        return self._execute_change(sql_text, target, operation="DML")

    def verify_table(self, target: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
        schema = str(target.get("schema") or "public")
        table = self._required(target, "table")
        expected_state = str(options.get("expected_state") or target.get("expected_state") or "exists").lower()
        rows = self._query(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
            ) AS exists
            """,
            [schema, table],
            target,
        )
        exists = bool(rows[0]["exists"]) if rows else False
        expected = expected_state not in {"missing", "not_exists", "deleted", "absent", "false", "0"}
        return {"schema": schema, "table": table, "exists": exists, "expected_exists": expected, "verified": exists == expected}

    def verify_columns(self, target: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
        result = self.list_columns(target)
        expected_columns = options.get("expected_columns")
        absent_columns = options.get("absent_columns") or []
        actual_names = {item["column_name"] for item in result["columns"]}
        missing = [str(name) for name in expected_columns or [] if str(name) not in actual_names]
        unexpectedly_present = [str(name) for name in absent_columns if str(name) in actual_names]
        result.update({
            "verified": not missing and not unexpectedly_present,
            "missing_expected_columns": missing,
            "unexpectedly_present_columns": unexpectedly_present,
        })
        return result

    def verify_data(self, sql_text: str, target: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
        rows = self._query(sql_text, [], target, allow_multi=False) if sql_text.strip() else self.read_data(target, options).get("rows", [])
        expected_count = options.get("expected_count")
        verified = True if expected_count is None else len(rows) == int(expected_count)
        return {"rows": rows, "count": len(rows), "expected_count": expected_count, "verified": verified}

    def _execute_change(self, sql_text: str, target: dict[str, Any], *, operation: str) -> dict[str, Any]:
        if not sql_text.strip():
            raise ValueError("실행할 SQL이 없다")
        driver_name, connection = self._connect(target)
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(sql_text, prepare=False) if driver_name == "psycopg" else cursor.execute(sql_text)
                rowcount = cursor.rowcount
                returned_rows = self._fetch_rows(cursor) if cursor.description else []
                connection.commit()
                return {"operation": operation, "executed": True, "rowcount": rowcount, "returned_rows": returned_rows}
            finally:
                cursor.close()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _query(self, sql_text: str, params: list[Any], target: dict[str, Any], *, allow_multi: bool = False) -> list[dict[str, Any]]:
        driver_name, connection = self._connect(target)
        try:
            cursor = connection.cursor()
            try:
                if not params:
                    if driver_name == "psycopg" and allow_multi:
                        cursor.execute(sql_text, prepare=False)
                    else:
                        cursor.execute(sql_text)
                elif driver_name == "psycopg" and allow_multi:
                    cursor.execute(sql_text, params, prepare=False)
                else:
                    cursor.execute(sql_text, params)
                rows = self._fetch_rows(cursor)
                connection.commit()
                return rows
            finally:
                cursor.close()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self, target: dict[str, Any]) -> tuple[str, Any]:
        registered = self.connections.get_default()
        connection_options = {
            key: value for key, value in registered.items()
            if key in {"host", "port", "dbname", "user", "password", "sslmode"}
        }
        try:
            import psycopg
            return "psycopg", psycopg.connect(**connection_options)
        except ImportError:
            try:
                import psycopg2
                return "psycopg2", psycopg2.connect(**connection_options)
            except ImportError as exc:
                raise RuntimeError("PostgreSQL 드라이버가 없다. 'pip install psycopg[binary]'를 실행한다") from exc

    def _fetch_rows(self, cursor: Any) -> list[dict[str, Any]]:
        if not cursor.description:
            return []
        names = [getattr(item, "name", item[0]) for item in cursor.description]
        return [{name: self._json_safe(value) for name, value in zip(names, row)} for row in cursor.fetchall()]

    @staticmethod
    def _required(target: dict[str, Any], name: str) -> str:
        value = target.get(name)
        if value in (None, ""):
            raise ValueError(f"target.{name} 값이 필요하다")
        return str(value)

    @staticmethod
    def _quote_identifier(value: str) -> str:
        if not IDENTIFIER_RE.fullmatch(value):
            raise ValueError(f"허용되지 않은 PostgreSQL 식별자다: {value}")
        return '"' + value.replace('"', '""') + '"'

    @staticmethod
    def _missing_result(exc: Exception) -> dict[str, Any] | None:
        sqlstate = str(getattr(exc, "sqlstate", "") or "")
        if sqlstate not in {"42703", "42P01"}:
            return None
        diagnostic = getattr(exc, "diag", None)
        missing_type = "column" if sqlstate == "42703" else "table"
        object_name = ""
        if diagnostic is not None:
            object_name = str(
                getattr(diagnostic, "column_name", "")
                or getattr(diagnostic, "table_name", "")
                or ""
            )
            if not object_name:
                primary = str(getattr(diagnostic, "message_primary", "") or "")
                matched = re.search(r'"([^"]+)"', primary)
                object_name = matched.group(1) if matched else ""
        type_label = "컬럼" if missing_type == "column" else "테이블"
        return {
            "rows": [],
            "count": 0,
            "exists": False,
            "query_executed": False,
            "missing_type": missing_type,
            "missing_name": object_name,
            "message": f"조회 대상 {type_label}이(가) 존재하지 않는다",
        }

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (bytes, bytearray, memoryview)):
            return base64.b64encode(bytes(value)).decode("ascii")
        if isinstance(value, (list, tuple)):
            return [DbService._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): DbService._json_safe(item) for key, item in value.items()}
        return str(value)
