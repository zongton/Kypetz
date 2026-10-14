# -*- coding: utf-8 -*-
"""
Kypetz 内置本地 HTTP 静态资源服务模块
用于为 QWebEngineView 提供绕过本地 file:// 跨域安全策略的 Live2D 资源静态服务。
"""

import os
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from core.config import PORT, BASE_DIR


def is_port_open(port: int) -> bool:
    """检查指定端口是否处于开放监听状态"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_server(port: int = PORT, directory: str = BASE_DIR) -> None:
    """启动本地守护 HTTP 静态服务"""
    if is_port_open(port):
        return

    class QuietHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, fmt, *args):
            pass  # 静默请求日志，保持控制台整洁

    def _serve():
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), QuietHandler)
            httpd.serve_forever()
        except Exception as e:
            print("[SERVER err]", e)

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
