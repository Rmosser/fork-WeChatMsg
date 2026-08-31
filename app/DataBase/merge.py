import hashlib
import os
import sqlite3
import uuid

from app.log import logger as APP_LOGGER

LOGGER = APP_LOGGER.getChild("merge")
_PRIVATE_MERGE_TOKEN = object()


def _path_label(value):
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()[:12]


def _assert_no_symlink_path(path_name, *, stop_at=None):
    current = os.path.abspath(path_name)
    # Callers pass a path whose parent is the controlled directory.  Do not
    # reject harmless platform aliases such as macOS /var -> /private/var;
    # reject the controlled directory itself and every component below the
    # optional trusted anchor.
    if stop_at is None:
        stop_at = os.path.abspath(os.sep)
    stop_at = os.path.abspath(stop_at)
    while True:
        # macOS exposes /var (and sometimes /tmp) as a stable platform alias
        # to /private/*; rejecting that alias would make every normal
        # TemporaryDirectory unusable.  Any symlink below those roots remains
        # rejected by the same lexical walk.
        platform_alias = current in {os.path.abspath("/var"), os.path.abspath("/tmp")}
        if os.path.lexists(current) and os.path.islink(current) and not platform_alias:
            raise RuntimeError(f"refusing symlink database path: {path_name}")
        if current == stop_at:
            return
        parent = os.path.dirname(current)
        if parent == current:
            return
        current = parent


def _assert_regular_database(path_name):
    if not os.path.lexists(path_name) or os.path.islink(path_name) or not os.path.isfile(path_name):
        raise RuntimeError(f"refusing non-regular database path: {path_name}")


def _readonly_connection(path_name):
    _assert_regular_database(path_name)
    connection = sqlite3.connect(f"file:{os.path.abspath(path_name)}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def read_message_receipt(path_name):
    """Read and validate a decrypted MSG database without changing it."""
    connection = _readonly_connection(path_name)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
        row_count = int(connection.execute("SELECT COUNT(*) FROM MSG").fetchone()[0])
        return {"integrity": integrity, "row_count": row_count}
    finally:
        connection.close()


def _copy_verified(source_path, destination_path):
    _assert_regular_database(source_path)
    if os.path.lexists(destination_path):
        raise FileExistsError(destination_path)
    source_stat = os.stat(source_path)
    digest = hashlib.sha256()
    try:
        with open(source_path, "rb") as source:
            fd = os.open(destination_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as destination:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
        copied_stat = os.stat(destination_path)
        copied_digest = hashlib.sha256()
        with open(destination_path, "rb") as copied:
            for chunk in iter(lambda: copied.read(1024 * 1024), b""):
                copied_digest.update(chunk)
        if copied_stat.st_size != source_stat.st_size or copied_digest.digest() != digest.digest():
            raise RuntimeError(f"database copy verification failed: {destination_path}")
    except Exception:
        try:
            os.unlink(destination_path)
        except FileNotFoundError:
            pass
        raise
    return destination_path


def build_merged_database(source_paths, temporary_path, *, run_id=None):
    """Build a complete shard merge in a private path before installation.

    The caller owns the final atomic replacement.  This function never writes to
    an existing target and leaves no temporary file when validation fails.
    """
    if not source_paths:
        raise ValueError("at least one source database is required")
    _assert_no_symlink_path(os.path.dirname(temporary_path))
    for source_path in source_paths:
        _assert_no_symlink_path(os.path.dirname(source_path))
        _assert_regular_database(source_path)
    try:
        _copy_verified(source_paths[0], temporary_path)
        first_rows = read_message_receipt(source_paths[0])["row_count"]
        summary = merge_databases(
            source_paths[1:],
            temporary_path,
            run_id=run_id,
            _internal_token=_PRIVATE_MERGE_TOKEN,
        )
        if summary["status"] != "complete":
            raise RuntimeError("one or more decrypted database shards are missing")
        receipt = read_message_receipt(temporary_path)
        if receipt["row_count"] != first_rows + summary["row_count"]:
            raise RuntimeError("merged database row-count verification failed")
        return receipt
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


def merge_databases(source_paths, target_path, *, run_id=None, _internal_token=None):
    """Merge shards into a run-private temporary database.

    Direct callers cannot nominate an existing user database as the target.
    The GUI's transaction builder is the only caller given the private module
    token; it creates the temporary target with an exclusive copy first and
    atomically installs it only after validation.
    """

    if _internal_token is not _PRIVATE_MERGE_TOKEN:
        raise RuntimeError(
            "direct database merge is disabled; use the run-scoped atomic builder"
        )
    run_id = run_id or uuid.uuid4().hex
    missing = []
    merged = 0
    row_count = 0
    target_parent = os.path.dirname(os.path.abspath(target_path))
    _assert_no_symlink_path(target_parent)
    target_name = os.path.basename(target_path)
    if not target_name.startswith(".") or not target_name.endswith(".tmp"):
        raise RuntimeError("merge target must be a private .tmp path")
    _assert_regular_database(target_path)
    # 创建目标数据库连接
    target_conn = sqlite3.connect(target_path)
    target_cursor = target_conn.cursor()
    try:
        # 开始事务
        target_conn.execute("BEGIN;")
        for i, source_path in enumerate(source_paths):
            if not os.path.exists(source_path):
                missing.append(source_path)
                continue
            _assert_no_symlink_path(os.path.dirname(source_path))
            _assert_regular_database(source_path)
            db = sqlite3.connect(source_path)
            try:
                cursor = db.cursor()
                sql = '''
                SELECT TalkerId,MsgsvrID,Type,SubType,IsSender,CreateTime,Sequence,StrTalker,StrContent,DisplayContent,BytesExtra
                FROM MSG;
                '''
                cursor.execute(sql)
                result = cursor.fetchall()
                # 附加源数据库
                target_cursor.executemany(
                    "INSERT INTO MSG "
                    "(TalkerId,MsgsvrID,Type,SubType,IsSender,CreateTime,Sequence,StrTalker,StrContent,DisplayContent,"
                    "BytesExtra)"
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    result)
                merged += 1
                row_count += len(result)
            finally:
                db.close()
        # 提交事务
        target_conn.execute("COMMIT;")

    except Exception:
        # 发生异常时回滚事务
        target_conn.execute("ROLLBACK;")
        LOGGER.exception(
            "database_merge_failed run_id=%s target_path_hash=%s merged=%d",
            run_id,
            _path_label(target_path),
            merged,
        )
        raise

    finally:
        # 关闭目标数据库连接
        target_conn.close()

    summary = {
        "run_id": run_id,
        "status": "complete" if not missing else "partial",
        "expected_count": len(source_paths),
        "merged_count": merged,
        "row_count": row_count,
        "missing": missing,
        "target_path": target_path,
    }
    LOGGER.info(
        "database_merge run_id=%s status=%s expected=%d merged=%d rows=%d missing=%d target_path_hash=%s",
        run_id,
        summary["status"],
        summary["expected_count"],
        merged,
        row_count,
        len(missing),
        _path_label(target_path),
    )
    if missing:
        LOGGER.warning(
            "database_merge_partial run_id=%s missing_path_hashes=%s",
            run_id,
            [_path_label(path) for path in missing],
        )
    return summary


if __name__ == "__main__":
    raise SystemExit(
        "The ad-hoc merge entry point is disabled. Use the GUI run-scoped merge "
        "which performs confirmation, backup, and atomic target replacement."
    )
