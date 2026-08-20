from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SQLColumn(BaseModel):
    name: str
    sql_type: str = Field(description="PostgreSQL type: TEXT, INTEGER, TIMESTAMPTZ, UUID, etc.")
    nullable: bool = True
    default: Optional[str] = None
    comment: Optional[str] = None


class SQLIndex(BaseModel):
    name: str
    columns: list[str]
    unique: bool = False


class ForeignKey(BaseModel):
    column: str
    references_table: str
    references_column: str
    on_delete: str = "CASCADE"


class DBTable(BaseModel):
    name: str = Field(description="Table name, snake_case")
    service_name: str = Field(description="Owning service")
    columns: list[SQLColumn]
    primary_key: list[str]
    foreign_keys: list[ForeignKey] = Field(default_factory=list)
    indexes: list[SQLIndex] = Field(default_factory=list)
    comment: Optional[str] = None


class DBSchema(BaseModel):
    tables: list[DBTable]
    raw_sql: str = Field(description="Complete SQLC-compatible CREATE TABLE SQL")
