#!/usr/bin/env python3
import argparse
import shutil
import sqlite3
import sys
import time
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_DIR / "local_sham_booking.db"
TABLES = ("tasks", "attempts", "pnr_records", "source_proxy_configs")


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def related_paths(db_path: Path) -> list[Path]:
    return [Path(str(db_path) + suffix) for suffix in ("", "-wal", "-shm")]


def timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def ps_quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def print_locked_file_help(db_path: Path, replacement_db: Path | None, stamp: str, error: PermissionError) -> None:
    print("")
    print(f"数据库文件仍被占用，无法替换: {error}")
    print("先关闭本地服务、PyCharm 运行窗口、PyCharm Database 面板或其他 SQLite 工具。")
    print("可在 PowerShell 查看/结束占用本项目的 Python 进程:")
    print(
        "  Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -like '*PycharmProjects\\\\order*' } | "
        "Select-Object ProcessId,CommandLine"
    )
    print(
        "  Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -like '*PycharmProjects\\\\order*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
    )
    if replacement_db:
        print("")
        print(f"恢复库已生成但尚未替换: {replacement_db}")
        print("停掉占用进程后，可手工替换:")
        print(f"  Rename-Item -LiteralPath {ps_quote(db_path)} -NewName {ps_quote(Path(db_path.name + '.malformed-' + stamp))}")
        for related in related_paths(db_path)[1:]:
            print(
                f"  if (Test-Path -LiteralPath {ps_quote(related)}) "
                f"{{ Rename-Item -LiteralPath {ps_quote(related)} -NewName {ps_quote(Path(related.name + '.malformed-' + stamp))} }}"
            )
        print(f"  Move-Item -LiteralPath {ps_quote(replacement_db)} -Destination {ps_quote(db_path)}")
        print(f"  .\\.venv\\Scripts\\python.exe tools\\sqlite_maintenance.py --db {ps_quote(db_path)} --check")


def backup_related_files(db_path: Path, stamp: str) -> Path:
    backup_dir = db_path.parent / "db_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for source in related_paths(db_path):
        if source.exists():
            backup = backup_dir / f"{source.name}.{stamp}.bak"
            shutil.copy2(source, backup)
            print(f"已备份: {source} -> {backup}")
    return backup_dir


def archive_related_files(db_path: Path, stamp: str) -> None:
    for source in related_paths(db_path):
        if source.exists():
            archive = source.with_name(f"{source.name}.malformed-{stamp}")
            source.replace(archive)
            print(f"已归档损坏文件: {source} -> {archive}")


def check_integrity(db_path: Path) -> tuple[bool, str]:
    if not db_path.exists():
        return True, "数据库文件不存在，启动服务时会自动创建。"
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError as exc:
        return False, f"完整性检查失败: {exc}"
    message = str(result[0] if result else "")
    return message.lower() == "ok", message or "无检查结果"


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall()
    except sqlite3.DatabaseError:
        return []
    return [row[1] for row in rows]


def copy_table(old_conn: sqlite3.Connection, new_conn: sqlite3.Connection, table: str) -> int:
    old_columns = table_columns(old_conn, table)
    new_columns = table_columns(new_conn, table)
    columns = [column for column in old_columns if column in new_columns]
    if not columns:
        return 0
    column_sql = ", ".join(quote_identifier(column) for column in columns)
    placeholder_sql = ", ".join("?" for _ in columns)
    rows = old_conn.execute(f"SELECT {column_sql} FROM {quote_identifier(table)}").fetchall()
    if not rows:
        return 0
    new_conn.executemany(
        f"INSERT OR REPLACE INTO {quote_identifier(table)} ({column_sql}) VALUES ({placeholder_sql})",
        [tuple(row) for row in rows],
    )
    return len(rows)


def create_empty_database(db_path: Path) -> None:
    sys.path.insert(0, str(PROJECT_DIR))
    from app.store import TaskStore

    TaskStore(db_path)


def rebuild_empty(db_path: Path) -> None:
    stamp = timestamp()
    backup_related_files(db_path, stamp)
    try:
        archive_related_files(db_path, stamp)
    except PermissionError as exc:
        print_locked_file_help(db_path, None, stamp, exc)
        raise RuntimeError("数据库文件被占用，请停止相关进程后重试 --rebuild-empty") from exc
    create_empty_database(db_path)
    ok, message = check_integrity(db_path)
    if not ok:
        raise RuntimeError(f"重建后完整性仍异常: {message}")
    print(f"已重建空数据库: {db_path}")


def recover_to_new_database(db_path: Path) -> None:
    if not db_path.exists():
        create_empty_database(db_path)
        print(f"数据库不存在，已创建空数据库: {db_path}")
        return

    stamp = timestamp()
    backup_related_files(db_path, stamp)
    temp_db = db_path.with_name(f"{db_path.name}.recovering-{stamp}")
    if temp_db.exists():
        temp_db.unlink()
    create_empty_database(temp_db)

    copied_counts: dict[str, int | str] = {}
    with sqlite3.connect(db_path) as old_conn, sqlite3.connect(temp_db) as new_conn:
        old_conn.row_factory = sqlite3.Row
        for table in TABLES:
            try:
                copied_counts[table] = copy_table(old_conn, new_conn, table)
            except sqlite3.DatabaseError as exc:
                copied_counts[table] = f"跳过: {exc}"
        new_conn.commit()

    try:
        archive_related_files(db_path, stamp)
        temp_db.replace(db_path)
    except PermissionError as exc:
        print_locked_file_help(db_path, temp_db, stamp, exc)
        raise RuntimeError("数据库文件被占用，请停止相关进程后手工替换或重试 --recover") from exc
    ok, message = check_integrity(db_path)
    if not ok:
        raise RuntimeError(f"恢复后完整性仍异常: {message}")
    print(f"已恢复到新数据库: {db_path}")
    for table, count in copied_counts.items():
        print(f"{table}: {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLite maintenance for Local Sham Booking.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite 数据库路径，默认 local_sham_booking.db")
    parser.add_argument("--check", action="store_true", help="只检查数据库完整性")
    parser.add_argument("--recover", action="store_true", help="备份原库并尽量恢复可读数据到新库")
    parser.add_argument("--rebuild-empty", action="store_true", help="备份原库并重建空数据库")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    if not any((args.check, args.recover, args.rebuild_empty)):
        args.check = True

    if args.check:
        ok, message = check_integrity(db_path)
        print(f"数据库: {db_path}")
        print(f"完整性: {'OK' if ok else '异常'} - {message}")
        return 0 if ok else 2
    if args.recover:
        recover_to_new_database(db_path)
        return 0
    if args.rebuild_empty:
        rebuild_empty(db_path)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
