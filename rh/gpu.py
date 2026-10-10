"""선택 기능: NVIDIA GPU 가속 팩 (cuBLAS + cuDNN).

앱에는 포함되어 있지 않고, 사용자가 허락했을 때만 NVIDIA 가 PyPI 에 올려 둔 공식 휠에서 필요한 DLL 만 꺼내 써요.
- 받는 곳: files.pythonhosted.org (PyPI 가 알려 주는 주소만, SHA-256 이 맞을 때만 사용)
- 저장 위치: %APPDATA%\\RabbitHaru\\gpu (지우면 바로 원래대로)
"""
import hashlib
import json
import re
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from .config import GPU_DIR

PACKAGES = ("nvidia-cublas-cu12", "nvidia-cudnn-cu12")
REQUIRED = ("cublas64_12.dll", "cudnn64_9.dll")
UA = {"User-Agent": "RHLingo"}
HOST = "https://files.pythonhosted.org/"


def installed(root=None):
    base = Path(root or GPU_DIR) / "nvidia"
    return base.is_dir() and all(any(base.glob(f"*/bin/{n}")) for n in REQUIRED)


def pack_info(fetch=None, timeout=20):
    """받을 파일 목록과 크기 (파일은 받지 않음). [{name, filename, url, size, sha256}]"""
    out = []
    for pkg in PACKAGES:
        url = f"https://pypi.org/pypi/{pkg}/json"
        if fetch is None:
            j = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read().decode("utf-8"))
        else:
            j = fetch(url)
        wheels = [u for u in j["urls"] if u["filename"].endswith("win_amd64.whl") and u["url"].startswith(HOST)]
        if not wheels:
            raise ValueError(f"no Windows wheel for {pkg}")
        w = wheels[0]
        out.append({"name": pkg, "filename": w["filename"], "url": w["url"], "size": int(w["size"]), "sha256": w["digests"]["sha256"].lower()})
    return out


def total_mb(info):
    return round(sum(i["size"] for i in info) / 1048576)


def download_pack(info, progress=None, dest=None, opener=None):
    """휠을 받아 SHA-256 을 확인한 뒤 DLL 만 풀어 놓음. 해시가 다르면 폐기하고 예외."""
    dest = Path(dest or GPU_DIR)
    total = sum(i["size"] for i in info)
    done = 0
    work = Path(tempfile.mkdtemp(prefix="rhl_gpu_"))
    stage = dest.with_name(dest.name + ".part")
    shutil.rmtree(stage, ignore_errors=True)
    try:
        for item in info:
            if not item["url"].startswith(HOST):
                raise ValueError("unexpected download host")
            wheel = work / re.sub(r"[^\w.\-]", "_", item["filename"])
            h = hashlib.sha256()
            req = urllib.request.Request(item["url"], headers=UA)
            with (opener or urllib.request.urlopen)(req, timeout=30) as r, open(wheel, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(min(99, int(done * 100 / total)))
            if h.hexdigest() != item["sha256"]:
                raise ValueError("checksum mismatch")
            with zipfile.ZipFile(wheel) as z:
                for m in z.namelist():
                    if re.match(r"^nvidia/[^/]+/bin/[^/]+\.dll$", m):
                        z.extract(m, stage)
            wheel.unlink()
        if not installed(stage):
            raise ValueError("required libraries missing in the download")
        shutil.rmtree(dest, ignore_errors=True)
        stage.replace(dest)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if progress:
            progress(None)


def remove_pack(dest=None):
    shutil.rmtree(Path(dest or GPU_DIR), ignore_errors=True)
