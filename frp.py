#!/usr/bin/env python3
"""Install frpc, generate frpc.toml, and start HTTP tunnels on macOS or Windows.

This single file has no third-party Python dependencies. It targets the FRP server
configured for task<port>.l-a-j.com HTTP tunnels.
"""

from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path


FRP_VERSION = "0.70.1"
DEFAULT_SERVER = "64.81.112.27"
DEFAULT_SERVER_PORT = 7000
DEFAULT_DOMAIN = "l-a-j.com"


def ask(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    prompt = f"{label}{suffix}: "
    value = input(prompt)
    return value.strip() or (default or "")


def ask_token() -> str:
    """Use a masked native dialog because IDE consoles can echo getpass input."""
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        token = simpledialog.askstring("FRP Token", "粘贴 FRP Token：", show="*", parent=root)
        root.destroy()
        return (token or "").strip()
    except Exception as error:
        raise RuntimeError("无法打开安全 Token 输入窗口。请在有桌面界面的 macOS 或 Windows 中运行。") from error


def ask_port_list() -> list[int]:
    while True:
        raw = ask("本机 HTTP 端口，逗号分隔", "8001,8292")
        try:
            ports = [int(item.strip()) for item in raw.split(",") if item.strip()]
            if not ports or any(port < 1 or port > 65535 for port in ports):
                raise ValueError
            if len(ports) != len(set(ports)):
                raise ValueError
            return ports
        except ValueError:
            print("请输入不重复的端口号，例如 8001,8292。")


def toml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def current_target() -> tuple[str, str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        os_name = "darwin"
        extension = "tar.gz"
    elif system == "windows":
        os_name = "windows"
        extension = "zip"
    else:
        raise RuntimeError("此工具仅支持 macOS 和 Windows。")

    if machine in {"arm64", "aarch64"}:
        arch = "arm64"
    elif machine in {"x86_64", "amd64"}:
        arch = "amd64"
    else:
        raise RuntimeError(f"不支持的处理器架构：{machine}")
    asset = f"frp_{FRP_VERSION}_{os_name}_{arch}.{extension}"
    return os_name, asset, extension


def download_frpc(install_dir: Path) -> Path:
    system, asset, extension = current_target()
    executable = install_dir / ("frpc.exe" if system == "windows" else "frpc")
    if executable.exists():
        return executable

    url = f"https://github.com/fatedier/frp/releases/download/v{FRP_VERSION}/{asset}"
    print(f"下载 FRP {FRP_VERSION}（{asset}）...")
    with tempfile.TemporaryDirectory(prefix="frp-setup-") as temp:
        temp_dir = Path(temp)
        archive = temp_dir / asset
        request = urllib.request.Request(url, headers={"User-Agent": "frp-http-client-setup"})
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)

        extracted = temp_dir / "extracted"
        extracted.mkdir()
        if extension == "zip":
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(extracted)
        else:
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(extracted)

        candidates = list(extracted.rglob("frpc.exe" if system == "windows" else "frpc"))
        if len(candidates) != 1:
            raise RuntimeError("下载包内未找到 frpc 可执行文件。")
        shutil.copy2(candidates[0], executable)
        if system != "windows":
            executable.chmod(0o700)
    return executable


def write_config(path: Path, server: str, server_port: int, token: str, domain: str, ports: list[int]) -> None:
    lines = [
        f"serverAddr = {toml_quote(server)}",
        f"serverPort = {server_port}",
        "",
        'auth.method = "token"',
        f"auth.token = {toml_quote(token)}",
    ]
    for port in ports:
        name = f"task{port}"
        lines.extend(
            [
                "",
                "[[proxies]]",
                f"name = {toml_quote(name)}",
                'type = "http"',
                'localIP = "127.0.0.1"',
                f"localPort = {port}",
                f"customDomains = [{toml_quote(f'{name}.{domain}')} ]",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def stop_previous(pid_file: Path) -> None:
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
    except (OSError, ValueError):
        pass
    pid_file.unlink(missing_ok=True)


def start_frpc(executable: Path, config: Path, install_dir: Path) -> int:
    pid_file = install_dir / "frpc.pid"
    stop_previous(pid_file)
    log_path = install_dir / "frpc.log"
    log = log_path.open("a", encoding="utf-8")
    kwargs: dict[str, object] = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": subprocess.STDOUT, "cwd": install_dir}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen([str(executable), "-c", str(config)], **kwargs)
    pid_file.write_text(str(process.pid), encoding="utf-8")
    return process.pid


def main() -> None:
    print("\nFRP HTTP 客户端一键部署\n")
    try:
        _, asset, _ = current_target()
        print(f"当前平台：{platform.system()} / {platform.machine()}，将使用 {asset}")
        server = ask("VPS 地址", DEFAULT_SERVER)
        server_port = int(ask("frps 端口", str(DEFAULT_SERVER_PORT)))
        if not 1 <= server_port <= 65535:
            raise ValueError("frps 端口必须介于 1 到 65535。")
        domain = ask("域名后缀", DEFAULT_DOMAIN).strip(".").lower()
        if not domain:
            raise ValueError("域名后缀不能为空。")
        token = ask_token()
        if not token:
            raise ValueError("FRP Token 不能为空。")
        ports = ask_port_list()
        default_dir = str(Path.home() / "frp-client")
        install_dir = Path(ask("安装目录", default_dir)).expanduser().resolve()
        install_dir.mkdir(parents=True, exist_ok=True)

        config = install_dir / "frpc.toml"
        write_config(config, server, server_port, token, domain, ports)
        executable = download_frpc(install_dir)
        result = subprocess.run([str(executable), "verify", "-c", str(config)], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or "frpc.toml 校验失败。")
        pid = start_frpc(executable, config, install_dir)

        print("\n部署完成：")
        print(f"  配置：{config}")
        print(f"  日志：{install_dir / 'frpc.log'}")
        print(f"  进程 PID：{pid}")
        for port in ports:
            print(f"  https://task{port}.{domain}  →  127.0.0.1:{port}")
    except Exception as error:
        print(f"\n部署失败：{error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
