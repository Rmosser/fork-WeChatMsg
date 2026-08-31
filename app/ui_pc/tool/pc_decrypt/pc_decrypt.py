import json
import hashlib
import os.path
import re
import time
import uuid

from PyQt5.QtCore import pyqtSignal, QThread, QUrl, QFile, QIODevice, QTextStream
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QWidget, QMessageBox, QFileDialog

from app.DataBase import msg, micro_msg, misc, hard_link
from app.DataBase.merge import build_merged_database, read_message_receipt
from app.decrypt import get_wx_info, decrypt
from app.log import logger
from app.util import path
from . import decryptUi


MSG_SHARD_RE = re.compile(r"^MSG(?:[0-9]|1[0-9])\.db$")


class DecryptControl(QWidget, decryptUi.Ui_Dialog):
    DecryptSignal = pyqtSignal(bool)
    get_wxidSignal = pyqtSignal(str)

    def __init__(self, parent=None):
        super(DecryptControl, self).__init__(parent)
        self.setupUi(self)

        self.pushButton_3.clicked.connect(self.decrypt)
        self.btn_getinfo.clicked.connect(self.get_info)
        self.btn_db_dir.clicked.connect(self.select_db_dir)
        self.lineEdit.returnPressed.connect(self.set_wxid)
        self.lineEdit.textChanged.connect(self.set_wxid_)
        self.btn_help.clicked.connect(self.show_help)
        self.info = {}
        self.lineEdit.setFocus()
        self.ready = False
        self.wx_dir = None

    def show_help(self):
        # 定义网页链接
        url = QUrl("https://blog.lc044.love/post/4")
        # 使用QDesktopServices打开网页
        QDesktopServices.openUrl(url)

    # @log
    def get_info(self):
        try:
            file = QFile(':/data/version_list.json')
            if file.open(QIODevice.ReadOnly | QIODevice.Text):
                stream = QTextStream(file)
                content = stream.readAll()
                file.close()
                VERSION_LIST = json.loads(content)
            else:
                return
            result = get_wx_info.get_info(VERSION_LIST)
            if result == -1:
                QMessageBox.critical(self, "错误", "请登录微信")
            elif result == -2:
                QMessageBox.critical(self, "错误", "微信版本不匹配\n请更新微信版本为:3.9.8.15")
            elif result == -3:
                QMessageBox.critical(self, "错误", "WeChat WeChatWin.dll Not Found")
            else:
                self.ready = True
                self.info = result[0]
                self.label_key.setText(self.info['key'])
                self.lineEdit.setText(self.info['wxid'])
                self.label_name.setText(self.info['name'])
                self.label_phone.setText(self.info['mobile'])
                self.label_pid.setText(str(self.info['pid']))
                self.label_version.setText(self.info['version'])
                self.lineEdit.setFocus()
                self.checkBox.setChecked(True)
                self.get_wxidSignal.emit(self.info['wxid'])
                directory = os.path.join(path.wx_path(), self.info['wxid'])
                if os.path.exists(directory):
                    self.label_db_dir.setText(directory)
                    self.wx_dir = directory
                    self.checkBox_2.setChecked(True)
                    self.ready = True
                if self.ready:
                    self.label_ready.setText('已就绪')
                if self.wx_dir and os.path.exists(os.path.join(self.wx_dir)):
                    self.label_ready.setText('已就绪')
        except Exception as e:
            QMessageBox.critical(self, "错误", "请登录微信")
            logger.error(
                "pc_wechat_info_failed error_type=%s",
                type(e).__name__,
                exc_info=True,
            )

    def set_wxid_(self):
        self.info['wxid'] = self.lineEdit.text()

    def set_wxid(self):
        self.info['wxid'] = self.lineEdit.text()
        QMessageBox.information(self, "ok", f"wxid修改成功{self.info['wxid']}")

    def select_db_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self, "选取微信文件保存目录——能看到Msg文件夹",
            path.wx_path()
        )  # 起始路径
        db_dir = os.path.join(directory, 'Msg')
        if not os.path.exists(db_dir):
            QMessageBox.critical(self, "错误", "文件夹选择错误\n一般以wxid_xxx结尾")
            return

        self.label_db_dir.setText(directory)
        self.wx_dir = directory
        self.checkBox_2.setChecked(True)
        if self.ready:
            self.label_ready.setText('已就绪')

    def decrypt(self):
        if not self.ready:
            QMessageBox.critical(self, "错误", "请先获取密钥")
            return
        if not self.wx_dir:
            QMessageBox.critical(self, "错误", "请先选择微信安装路径")
            return
        if self.lineEdit.text() == 'None':
            QMessageBox.critical(self, "错误", "请填入wxid")
            return
        db_dir = os.path.join(self.wx_dir, 'Msg')
        if self.ready:
            if not os.path.exists(db_dir):
                QMessageBox.critical(self, "错误", "文件夹选择错误\n一般以wxid_xxx结尾")
                return

        self.thread2 = DecryptThread(db_dir, self.info['key'])
        self.thread2.maxNumSignal.connect(self.setProgressBarMaxNum)
        self.thread2.signal.connect(self.progressBar_view)
        self.thread2.okSignal.connect(self.btnExitClicked)
        self.thread2.start()

    def btnEnterClicked(self):
        # print("enter clicked")
        # 中间可以添加处理逻辑
        # QMessageBox.about(self, "解密成功", "数据库文件存储在app/DataBase/Msg文件夹下")

        self.DecryptSignal.emit(True)
        # self.close()

    def setProgressBarMaxNum(self, max_val):
        self.progressBar.setRange(0, max_val)

    def progressBar_view(self, value):
        """
        进度条显示
        :param value: 进度0-100
        :return: None
        """
        self.progressBar.setProperty('value', value)
        #     self.btnExitClicked()
        #     data.init_database()

    def btnExitClicked(self, status='ok'):
        # print("Exit clicked")
        if status != 'ok':
            logger.error(
                "pc_decrypt_incomplete run_id=%s status=%s",
                getattr(self.thread2, 'run_id', '<unknown>'),
                status,
            )
            QMessageBox.critical(self, "错误", "数据库解密未完成，请检查错误日志")
            return
        dic = {
            'wxid': self.info['wxid'],
            'wx_dir': self.wx_dir,
            'name': self.info['name'],
            'mobile': self.info['mobile']
        }
        try:
            if not os.path.exists('./app/data'):
                os.mkdir('./app/data')
            with open('./app/data/info.json', 'w', encoding='utf-8') as f:
                f.write(json.dumps(dic))
        except:
            with open('./info.json', 'w', encoding='utf-8') as f:
                f.write(json.dumps(dic))
        # 目标数据库文件
        target_database = "app/DataBase/Msg/MSG.db"
        # Only merge shards produced by this run's unique output directory.
        source_databases = list(getattr(self.thread2, 'output_databases', []))
        if not source_databases:
            QMessageBox.critical(self, "错误", "没有可合并的解密数据库分片")
            return
        run_id = getattr(self.thread2, 'run_id', uuid.uuid4().hex)
        try:
            target_parent = os.path.dirname(target_database)
            _assert_no_symlink_path(target_parent)
            for source_database in source_databases:
                _assert_regular_file(source_database)

            # Build and validate the complete result in a private same-directory
            # database.  Never replace the user's database until every shard has
            # merged and the resulting SQLite file has passed integrity/readback.
            temporary_database = os.path.join(
                target_parent,
                f".{os.path.basename(target_database)}.{run_id}.{uuid.uuid4().hex}.tmp",
            )
            target_stat = None
            backup_database = None
            backup_receipt = None
            backup_message_receipt = None
            candidate_receipt = None
            try:
                receipt = build_merged_database(source_databases, temporary_database, run_id=run_id)
                candidate_receipt = _file_receipt(temporary_database)

                if os.path.lexists(target_database):
                    _assert_regular_file(target_database)
                    target_stat = os.lstat(target_database)
                    answer = QMessageBox.question(
                        self,
                        "确认覆盖数据库",
                        "目标数据库已存在。覆盖前会创建带运行 ID 的备份，是否继续？",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if answer != QMessageBox.Yes:
                        logger.info("pc_database_merge_cancelled run_id=%s reason=target_exists", run_id)
                        return
                    backup_database = _exclusive_copy(target_database, f"{target_database}.bak.{run_id}")
                    backup_receipt = _file_receipt(backup_database)
                    backup_message_receipt = read_message_receipt(backup_database)
                    logger.info("pc_database_backup_created run_id=%s path=%s", run_id, backup_database)
                    # Confirmation and backup must both precede the final
                    # replacement, and the original inode must still be present.
                    _assert_same_file(target_database, target_stat)

                _atomic_replace_verified(temporary_database, target_database, expected_stat=target_stat)
                final_receipt = read_message_receipt(target_database)
                if final_receipt['row_count'] != receipt['row_count']:
                    raise RuntimeError("installed database row-count verification failed")
                temporary_database = None
            except Exception:
                # If an unexpected post-replacement verification failure occurs,
                # restore the pre-run backup.  All normal merge failures happen
                # before replacement and therefore leave the original untouched.
                if backup_database and os.path.lexists(backup_database):
                    try:
                        _assert_regular_file(backup_database)
                        # Never overwrite an unrelated file while recovering.
                        # If replacement already happened, the current target
                        # must still be the candidate produced by this run.
                        if os.path.lexists(target_database):
                            if os.path.islink(target_database):
                                raise RuntimeError("database target became a symlink during recovery")
                            if target_stat is not None:
                                current = os.lstat(target_database)
                                if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) == (
                                    target_stat.st_dev,
                                    target_stat.st_ino,
                                        target_stat.st_size,
                                        target_stat.st_mtime_ns,
                                    ):
                                    # The atomic replace did not happen; the
                                    # original target remains authoritative.
                                    logger.warning(
                                        "pc_database_recovery_not_needed run_id=%s reason=target_unchanged",
                                        run_id,
                                    )
                                    raise _RecoveryNotNeeded
                            if candidate_receipt is None or _file_receipt(target_database) != candidate_receipt:
                                raise RuntimeError("refusing to overwrite an unrelated target during recovery")
                        os.replace(backup_database, target_database)
                        if backup_receipt is None or _file_receipt(target_database) != backup_receipt:
                            raise RuntimeError("restored database backup receipt mismatch")
                        restored = read_message_receipt(target_database)
                        if backup_message_receipt is None or restored != backup_message_receipt:
                            raise RuntimeError("restored database integrity readback mismatch")
                        backup_database = None
                    except _RecoveryNotNeeded:
                        pass
                    except Exception:
                        logger.error("pc_database_restore_failed run_id=%s", run_id, exc_info=True)
                elif target_stat is None and candidate_receipt is not None and os.path.lexists(target_database):
                    # No prior target existed.  Remove only the verified
                    # candidate installed by this run; never unlink an
                    # unrelated path after a failed post-install check.
                    try:
                        _assert_regular_file(target_database)
                        if _file_receipt(target_database) == candidate_receipt:
                            os.unlink(target_database)
                            if os.path.lexists(target_database):
                                raise RuntimeError("failed database install target still exists")
                        else:
                            raise RuntimeError("refusing to remove unrelated database target")
                    except Exception:
                        logger.error("pc_database_uninstall_failed run_id=%s", run_id, exc_info=True)
                raise
            finally:
                if temporary_database:
                    try:
                        os.unlink(temporary_database)
                    except FileNotFoundError:
                        pass
        except Exception as e:
            logger.error(
                "pc_database_merge_failed run_id=%s error_type=%s",
                run_id,
                type(e).__name__,
                exc_info=True,
            )
            QMessageBox.critical(self, "错误", "数据库合并失败，请检查错误日志")
            return
        self.DecryptSignal.emit(True)
        self.close()


def _assert_no_symlink_path(path_name):
    """Reject symlinks in the controlled output path before any write."""
    current = os.path.abspath(path_name)
    while True:
        if os.path.lexists(current) and os.path.islink(current):
            raise RuntimeError(f"refusing symlink output path: {path_name}")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent


def _assert_regular_file(path_name):
    if not os.path.lexists(path_name) or os.path.islink(path_name) or not os.path.isfile(path_name):
        raise RuntimeError(f"refusing non-regular database path: {path_name}")


class _RecoveryNotNeeded(Exception):
    """Internal marker: atomic replacement did not occur."""


def _file_receipt(path_name):
    """Return a content receipt without following symlinks."""
    _assert_regular_file(path_name)
    digest = hashlib.sha256()
    with open(path_name, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"size_bytes": os.stat(path_name).st_size, "sha256": digest.hexdigest()}


def _assert_same_file(path_name, expected_stat):
    _assert_regular_file(path_name)
    current = os.lstat(path_name)
    if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
        expected_stat.st_dev,
        expected_stat.st_ino,
        expected_stat.st_size,
        expected_stat.st_mtime_ns,
    ):
        raise RuntimeError("database target changed after confirmation")


def _copy_with_receipt(source_name, destination_name):
    _assert_regular_file(source_name)
    _assert_no_symlink_path(os.path.dirname(destination_name))
    source_stat = os.stat(source_name)
    digest = hashlib.sha256()
    try:
        with open(source_name, "rb") as source:
            with os.fdopen(os.open(destination_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as destination:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
        installed_stat = os.stat(destination_name)
        if installed_stat.st_size != source_stat.st_size:
            raise RuntimeError(f"database backup size mismatch: {destination_name}")
        check = hashlib.sha256()
        with open(destination_name, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                check.update(chunk)
        if check.digest() != digest.digest():
            raise RuntimeError(f"database backup hash mismatch: {destination_name}")
    except Exception:
        try:
            os.unlink(destination_name)
        except FileNotFoundError:
            pass
        raise
    return destination_name


def _exclusive_copy(source_name, requested_destination):
    for index in range(100):
        destination = requested_destination if index == 0 else f"{requested_destination}.{index}"
        try:
            return _copy_with_receipt(source_name, destination)
        except FileExistsError:
            continue
    raise RuntimeError(f"could not create exclusive database backup: {requested_destination}")


def _atomic_install(source_name, target_name, expected_stat=None):
    _assert_regular_file(source_name)
    _assert_no_symlink_path(os.path.dirname(target_name))
    if expected_stat is not None:
        _assert_regular_file(target_name)
        current = os.lstat(target_name)
        if (current.st_dev, current.st_ino) != (expected_stat.st_dev, expected_stat.st_ino):
            raise RuntimeError("database target changed after confirmation")
    temporary = os.path.join(os.path.dirname(target_name), f".{os.path.basename(target_name)}.{uuid.uuid4().hex}.tmp")
    try:
        _copy_with_receipt(source_name, temporary)
        if os.path.lexists(target_name) and os.path.islink(target_name):
            raise RuntimeError("database target became a symlink")
        if expected_stat is None and os.path.lexists(target_name):
            raise RuntimeError("database target appeared during atomic install")
        os.replace(temporary, target_name)
        _assert_regular_file(target_name)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _atomic_replace_verified(source_name, target_name, expected_stat=None):
    """Replace a database only after source validation and target identity check."""
    _assert_regular_file(source_name)
    _assert_no_symlink_path(os.path.dirname(target_name))
    if expected_stat is not None:
        _assert_same_file(target_name, expected_stat)
    elif os.path.lexists(target_name):
        raise RuntimeError("database target appeared during atomic replacement")
    os.replace(source_name, target_name)
    _assert_regular_file(target_name)


class DecryptThread(QThread):
    signal = pyqtSignal(str)
    maxNumSignal = pyqtSignal(int)
    okSignal = pyqtSignal(str)

    def __init__(self, db_path, key):
        super(DecryptThread, self).__init__()
        self.db_path = db_path
        self.key = key
        self.textBrowser = None
        self.run_id = uuid.uuid4().hex
        self.output_dir = None
        self.output_databases = []

    def __del__(self):
        pass

    def run(self):
        misc.close()
        msg.close()
        micro_msg.close()
        hard_link.close()
        QThread.sleep(1)
        # Both the input tree and the run root are repository-controlled.  Do
        # this before mkdir/os.walk so a pre-existing Msg or ancestor symlink
        # cannot redirect decrypted output outside the checkout.
        _assert_no_symlink_path(self.db_path)
        # data.decrypt(self.db_path, self.key)
        # decrypt.decrypt opens output files with wb.  Keep every run in a
        # fresh, private directory so a source shard can never replace an
        # existing database or a shard from another run.
        output_dir = os.path.join('app', 'DataBase', 'Msg', '.decrypt-runs', self.run_id)
        _assert_no_symlink_path(os.path.join('app', 'DataBase', 'Msg'))
        _assert_no_symlink_path(os.path.dirname(output_dir))
        if os.path.lexists(os.path.dirname(output_dir)) and not os.path.isdir(os.path.dirname(output_dir)):
            raise RuntimeError("decrypt run root is not a directory")
        os.makedirs(output_dir, mode=0o700, exist_ok=False)
        _assert_no_symlink_path(output_dir)
        self.output_dir = output_dir
        tasks = []
        allocated_outputs = set()
        if os.path.exists(self.db_path):
            discovered = []
            seen_shard_indices = {}
            for root, dirs, files in os.walk(self.db_path, topdown=True):
                dirs.sort()
                files.sort()
                for directory in dirs:
                    if os.path.islink(os.path.join(root, directory)):
                        raise RuntimeError("refusing symlink in decrypted database input tree")
                for file in files:
                    match = MSG_SHARD_RE.fullmatch(file)
                    if match is None:
                        continue
                    inpath = os.path.join(root, file)
                    _assert_regular_file(inpath)
                    relative = os.path.relpath(inpath, self.db_path)
                    shard_index = int(file[3:-3])
                    previous = seen_shard_indices.get(shard_index)
                    if previous is not None:
                        raise RuntimeError(
                            "duplicate message shard index "
                            f"MSG{shard_index}.db: {previous} and {inpath}"
                        )
                    seen_shard_indices[shard_index] = inpath
                    discovered.append((relative, inpath, shard_index))
            # Keep the original MSG0..MSG19 shard contract and make traversal
            # deterministic.  Other *.db files (MicroMsg, MediaMSG, etc.) are
            # not message shards and must never be merged into MSG.
            discovered.sort(key=lambda item: (os.path.dirname(item[0]), item[2], item[0]))
            for relative, inpath, _ in discovered:
                output_path = os.path.join(output_dir, relative)
                output_parent = os.path.dirname(output_path)
                _assert_no_symlink_path(output_parent)
                os.makedirs(output_parent, mode=0o700, exist_ok=True)
                if output_path in allocated_outputs:
                    raise RuntimeError("duplicate decrypted database output path")
                allocated_outputs.add(output_path)
                tasks.append([self.key, inpath, output_path])
        self.output_databases = [task[2] for task in tasks]
        self.maxNumSignal.emit(len(tasks))
        failures = []
        for i, task in enumerate(tasks):
            try:
                result = decrypt.decrypt(*task)
                if not isinstance(result, dict) or result.get('ok') is not True:
                    failures.append(i)
                    logger.error(
                        "pc_decrypt_task_failed run_id=%s index=%d result=%s",
                        self.run_id,
                        i,
                        result,
                    )
            except Exception as e:
                failures.append(i)
                logger.error(
                    "pc_decrypt_task_failed run_id=%s index=%d error_type=%s",
                    self.run_id,
                    i,
                    type(e).__name__,
                    exc_info=True,
                )
            self.signal.emit(str(i))
        if not tasks:
            failures.append('no_tasks')
        if failures:
            logger.error(
                "pc_decrypt_incomplete run_id=%s task_count=%d failure_count=%d failure_indexes=%s",
                self.run_id,
                len(tasks),
                len(failures),
                failures[:20],
            )
            self.okSignal.emit('failed')
        else:
            logger.info(
                "pc_decrypt_complete run_id=%s task_count=%d",
                self.run_id,
                len(tasks),
            )
            self.okSignal.emit('ok')
        # self.signal.emit('100')


class MyThread(QThread):
    signal = pyqtSignal(str)

    def __init__(self):
        super(MyThread, self).__init__()

    def __del__(self):
        pass

    def run(self):
        for i in range(100):
            self.signal.emit(str(i))
            time.sleep(0.1)
