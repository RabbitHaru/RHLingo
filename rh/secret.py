"""API 키 같은 비밀 값을 Windows DPAPI 로 암호화해 저장 (현재 Windows 사용자 계정에서만 복호화 가능)."""
import base64
import ctypes
from ctypes import wintypes


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _make(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _crypt(data, protect):
    blob_in, keep = _make(data)
    blob_out = _Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    args = (ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)) if protect else \
        (ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not fn(*args):
        raise OSError("DPAPI failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def encrypt(text):
    return base64.b64encode(_crypt(text.encode("utf-8"), True)).decode("ascii") if text else ""


def decrypt(token):
    try:
        return _crypt(base64.b64decode(token), False).decode("utf-8") if token else ""
    except Exception:
        return ""  # 다른 PC/계정으로 옮겨진 설정이면 키가 비어 있는 것으로 처리
