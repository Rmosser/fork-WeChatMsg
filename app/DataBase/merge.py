import hashlib
import os
import sqlite3
import uuid

from app.log import logger as APP_LOGGER

LOGGER = APP_LOGGER.getChild("merge")


def _path_label(value):
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()[:12]


def merge_databases(source_paths, target_path, *, run_id=None):
    run_id = run_id or uuid.uuid4().hex
    missing = []
    merged = 0
    row_count = 0
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
    # 源数据库文件列表
    source_databases = ["Msg/MSG1.db", "Msg/MSG2.db", "Msg/MSG3.db"]

    # 目标数据库文件
    target_database = "Msg/MSG.db"
    import shutil

    shutil.copy('Msg/MSG0.db', target_database)  # 使用一个数据库文件作为模板
    # 合并数据库
    merge_databases(source_databases, target_database)
