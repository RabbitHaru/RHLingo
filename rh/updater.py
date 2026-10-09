"""새 버전 확인과 설치 파일 업데이트.

- 확인: GitHub 릴리스 목록을 읽기만 합니다 (사용자 동의/요청이 있을 때만 호출됨).
- 설치: 설치 프로그램(Setup .exe)을 받아 SHA-256 을 확인한 뒤, 사용자가 허락했을 때만 실행합니다.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

UA = {"User-Agent": "RHLingo"}


def version_key(v):
    """'1.0.0-beta.2' < '1.0.0-beta.10' < '1.0.0' < '1.0.1'. 정식 버전이 같은 숫자의 베타보다 높아요."""
    v = v.lstrip("vV")
    main, _, pre = v.partition("-")
    nums = tuple(int(x) for x in re.findall(r"\d+", main)[:3])
    nums += (0,) * (3 - len(nums))
    if not pre:
        return nums + (1, "", 0)
    m = re.match(r"([A-Za-z]+)\.?(\d*)", pre)
    return nums + (0, (m.group(1).lower() if m else pre), int(m.group(2) or 0) if m else 0)


def is_installed():
    """설치 마법사로 설치된 앱인지 (exe 옆에 제거 프로그램이 있는지)."""
    if not getattr(sys, "frozen", False):
        return False
    return any(Path(sys.executable).parent.glob("unins*.exe"))


def _installer_asset(release, repo):
    prefix = f"https://github.com/{repo}/releases/download/"
    for a in release.get("assets", []):
        name, url = a.get("name", ""), a.get("browser_download_url", "")
        if re.search(r"setup.*\.exe$", name, re.I) and url.startswith(prefix):
            digest = (a.get("digest") or "")
            sha = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else ""
            return {"name": name, "url": url, "size": int(a.get("size") or 0), "sha256": sha}
    return None


def find_update(current, repo, fetch=None, timeout=10):
    """현재 버전보다 새로운 릴리스를 찾아요. 없으면 None. 베타 사용자는 베타도, 정식 사용자는 정식만 봐요."""
    url = f"https://api.github.com/repos/{repo}/releases?per_page=15"
    if fetch is None:
        req = urllib.request.Request(url, headers={**UA, "Accept": "application/vnd.github+json"})
        data = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
    else:
        data = fetch(url)
    include_pre = "-" in current
    best = None
    for r in data:
        tag = (r.get("tag_name") or "").lstrip("vV")
        if r.get("draft") or not tag or (r.get("prerelease") and not include_pre):
            continue
        if version_key(tag) > version_key(current) and (best is None or version_key(tag) > version_key(best["version"])):
            best = {"version": tag, "page": r.get("html_url", f"https://github.com/{repo}/releases"),
                    "installer": _installer_asset(r, repo)}
    return best


def download_installer(asset, progress=None, dest_dir=None, opener=None):
    """설치 파일을 받아 SHA-256 을 확인한 경로를 돌려줘요. 체크섬이 없거나 다르면 지우고 예외."""
    if not asset or not asset.get("sha256"):
        raise ValueError("no checksum")
    dest_dir = Path(dest_dir or tempfile.gettempdir()) / "RHLingo-update"
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / re.sub(r"[^\w.\-]", "_", asset["name"])
    req = urllib.request.Request(asset["url"], headers=UA)
    h = hashlib.sha256()
    with (opener or urllib.request.urlopen)(req, timeout=20) as r, open(path, "wb") as out:
        total = int(r.headers.get("Content-Length") or asset.get("size") or 0)
        done = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if h.hexdigest() != asset["sha256"]:
        try:
            path.unlink()
        except OSError:
            pass
        raise ValueError("checksum mismatch")
    return path


def launch_installer(path):
    """조용히 설치하고 끝나면 앱을 다시 켜는 옵션으로 실행 (호출한 쪽이 곧바로 앱을 종료해야 해요)."""
    subprocess.Popen([str(path), "/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS", "/LAUNCH=1"],
                     close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
