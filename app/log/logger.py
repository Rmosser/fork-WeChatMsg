import logging
import hashlib
import inspect
import os
import re
import time
import traceback
from functools import wraps

filename = time.strftime("%Y-%m-%d", time.localtime(time.time()))
logger = logging.getLogger('test')
logger.setLevel(level=logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s')
try:
    if not os.path.exists('./app/log/logs'):
        os.mkdir('./app/log/logs')
    file_handler = logging.FileHandler(f'./app/log/logs/{filename}-log.log')
except:
    file_handler = logging.FileHandler(f'{filename}-log.log')

file_handler.setLevel(level=logging.INFO)
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

_SECRET_FIELD_NAMES = {
    'key', 'token', 'access_token', 'api_key', 'apikey', 'password',
    'passwd', 'authorization', 'cookie', 'sid', 'session', 'secret',
}
_IDENTITY_FIELD_NAMES = {
    'account', 'mobile', 'mail', 'wxid', 'filepath', 'path', 'db_path',
    'out_path', 'outpath', 'url', 'uri',
}
_DATA_FIELD_NAMES = {
    'content', 'message', 'messages', 'body', 'template', 'displaycontent',
    'strcontent', 'kwargs', 'args',
}
_SENSITIVE_QUERY_RE = re.compile(
    r'([?&](?:token|access_token|api_key|apikey|key|secret|password|passwd|auth|authorization|cookie|sid)=)[^&#\s]*',
    re.IGNORECASE,
)
_URL_USERINFO_RE = re.compile(r'(\b[a-z][a-z0-9+.-]*://)[^/\s@]+@', re.IGNORECASE)


def _digest(value):
    return hashlib.sha256(str(value).encode('utf-8', errors='replace')).hexdigest()[:12]


def _redact_text(value):
    text = str(value)
    text = _URL_USERINFO_RE.sub(r'\1<redacted>@', text)
    return _SENSITIVE_QUERY_RE.sub(r'\1<redacted>', text)


def safe_log_value(name, value):
    """Return a low-cardinality, non-secret representation for diagnostics."""
    normalized = str(name).lower().replace('-', '_')
    if normalized in _SECRET_FIELD_NAMES:
        return '<present>' if value not in (None, '', 'None') else '<missing>'
    if normalized in _IDENTITY_FIELD_NAMES:
        if value in (None, '', 'None'):
            return value
        return f'<hash:{_digest(value)}>'
    if normalized in _DATA_FIELD_NAMES:
        if value in (None, '', 'None'):
            return value
        return f'<hash:{_digest(value)}>'
    return _redact_text(value)


def safe_log_object(value, field_name=''):
    """Recursively redact decorator arguments before writing them to a log."""
    if isinstance(value, dict):
        return {str(key): safe_log_value(key, item) if not isinstance(item, (dict, list, tuple))
                else safe_log_object(item, str(key)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_log_object(item, field_name) for item in value]
    if field_name:
        return safe_log_value(field_name, value)
    return _redact_text(value)


def log(func):
    signature = inspect.signature(func)

    @wraps(func)
    def log_(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            try:
                bound = signature.bind_partial(*args, **kwargs)
                safe_params = {
                    name: safe_log_object(value, name)
                    for name, value in bound.arguments.items()
                }
            except (TypeError, ValueError):
                safe_params = safe_log_object((args, kwargs))
            logger.error(
                f"\n{func.__qualname__} is error,params:{safe_params},"
                "here are details:",
                exc_info=True,
            )
            raise

    return log_
