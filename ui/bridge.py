# -*- coding: utf-8 -*-
"""
Kypetz QWebChannel 桥接服务模块
负责 Python 后端与 WebEngine 前端 Live2D Stage 的双向实时通信与事件映射。
"""

from PySide6.QtCore import QObject, Signal, Slot, QPoint
from core.config import result_queue
from audio.chimes import play_chime, CHIME_SENT
from audio.player import _ui_sig


class JsBridge(QObject):
    """向前端 JavaScript 发送任意评估指令的信号管道"""
    eval_js = Signal(str)

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.eval_js.connect(self._do)

    def _do(self, js: str) -> None:
        try:
            self.view.page().runJavaScript(js)
        except Exception as e:
            print("[JS bridge err]", e)


class MoveObj(QObject):
    """前端 Live2D 画布向宿主 Python 发起的拖拽位移与打字输入回调对象"""

    def __init__(self, win):
        super().__init__(win)
        self.win = win

    @Slot(int, int)
    def move_by(self, dx: int, dy: int) -> None:
        """窗口坐标相对移动"""
        self.win.move(self.win.pos() + QPoint(int(dx), int(dy)))

    @Slot(str)
    def send_user_text(self, text: str) -> None:
        """接收前端打字输入框发送的用户文本"""
        t = (text or "").strip()
        print(f"[User][Input] 收到前端文本输入: '{t}'")
        if t:
            play_chime(CHIME_SENT)
            _ui_sig.show_user.emit(t)
            result_queue.put(t)
