# -*- coding: utf-8 -*-
"""
Kypetz (AI Desktop Pet) — 主程序入口
高内聚解耦架构：负责应用生命周期管理、事件调度、热键监听及挂机主动互动。
"""

import sys
import os
import time
import json
import random
import threading

# 1. 启动自愈诊断舱 (极简原生 Tkinter 流水线，在导入任何三方依赖前先执行环境自检与自愈)
from ui.splash import run_self_healing_splash
run_self_healing_splash()

# 2. 安全导入基础第三方依赖
try:
    import keyboard
except ImportError:
    keyboard = None

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QFont, QColor, QCursor
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel

# 3. 导入核心层、音频层与界面层模块
from core.config import (
    APP_NAME, APP_VERSION, PORT, _cfg, save_config,
    result_queue, _recording, _tts_lock, _is_speaking, _last_user_activity,
    _log_emitter, StdoutRedirector
)
from core.server import ensure_server
from core.llm import llm_ask, fetch_models
from core.action import parse_ai_action, is_action_only, mood_sound, strip_action_tags, clean_display_text, get_model_capabilities
from core.llm import llm_ask, fetch_models, llm_ask_proactive
from audio.chimes import play_chime, CHIME_START
from audio.player import _ui_sig
from audio.speech import speak, warmup_sovits
from audio.recognizer import record_and_recognize
from ui.widgets import SVGS, make_svg_icon, AppleDragHandle, AppleControlBar
from ui.bridge import JsBridge, MoveObj
from ui.dashboard import KypetzDashboard

# 窗口初始几何尺寸
WM_W, WM_H = 340, 500


def process(text: str, bridge: JsBridge) -> None:
    """交互处理流水线：LLM 对话生成、动作指令解析与语音合成调度"""
    if not text:
        return
    _last_user_activity[0] = time.time()
    pet_name = _cfg.get("pet_name", "桌宠").strip() or "桌宠"
    _ui_sig.status.emit(f"{pet_name}思考中…")
    reply = llm_ask(text)
    print(f"[{pet_name}] '{text}' -> '{reply}'")

    # 动作与表情意图解析 (直接驱动模型演出)
    mot, exp = parse_ai_action(reply)
    print(f"[{pet_name}][Action] 驱动模型表演: motion='{mot}', expression='{exp}'")

    # 桌面气泡展示文本：彻底抹去机器指令 [action: ...]，只给用户看纯净台词
    display_reply = clean_display_text(reply)

    # 语音发音文本：剥离机器指令与多余动作括号
    if is_action_only(reply):
        voice_text = mood_sound(reply)
    else:
        clean_speech = strip_action_tags(reply)
        voice_text = clean_speech if clean_speech else mood_sound(reply)

    # 传给 speak 音频流水线，在发声瞬间毫秒级音画同步驱动模型动作与纯净字幕
    speak(text, display_reply, voice_text, mot, exp)


def _drain(q, br: JsBridge) -> None:
    """轮询消费用户输入队列"""
    try:
        while True:
            item = q.get_nowait()
            if item:
                threading.Thread(target=process, args=(item, br), daemon=True).start()
    except Exception:
        pass


def idle_companion_loop(win) -> None:
    """
    真实自主思考的闲时主动互动引擎：
    彻底废除固定死板的静态预设，挂机超过 1 分钟后，随机调度真实大模型 API，
    让角色根据当前人设性格自主构思话题、主动寻找主人搭话并做动作！
    """
    last_proactive_time = time.time()
    while True:
        time.sleep(random.uniform(15, 25))
        now = time.time()
        idle_time = now - _last_user_activity[0]

        # 录音中、发声中、锁定时跳过，绝不打扰用户
        if _recording[0] or _is_speaking.is_set() or _tts_lock.locked():
            continue

        # 1. 挂机超 15 秒且小于 60 秒：低调微动作自娱自乐 (从当前模型真实可用动作中选取)
        if 15 < idle_time < 60 and random.random() < 0.40:
            m_list, _ = get_model_capabilities()
            if m_list:
                mot = random.choice(m_list[:8])
                win.bridge.eval_js.emit(f"window.setMotion && window.setMotion('{mot}')")

        # 2. 挂机超过 60 秒：真实调用 API 自主找话题搭话！
        elif idle_time >= 60 and (now - last_proactive_time) > random.uniform(60, 120):
            last_proactive_time = now
            _last_user_activity[0] = now  # 刷新活跃时间防高频打扰

            pet_name = _cfg.get("pet_name", "桌宠").strip() or "桌宠"
            user_call = _cfg.get("user_call", "主人").strip() or "主人"
            cur_model = _cfg.get("live2d_model", "")

            print(f"[{pet_name}][Idle] 用户静置超过 1 分钟，大模型正在主动构思话题...")
            _ui_sig.status.emit(f"{pet_name}正在想事情…")

            try:
                reply = llm_ask_proactive(pet_name, user_call, cur_model)
                if reply and reply.strip():
                    print(f"[{pet_name}][Idle] 主动发起话题: '{reply}'")
                    mot, exp = parse_ai_action(reply)
                    voice_text = strip_action_tags(reply)
                    display_reply = clean_display_text(reply)
                    speak("主动搭话", display_reply, voice_text, mot, exp)
            except Exception as e:
                print(f"[{pet_name}][Idle err]", e)
                _ui_sig.status.emit("按住 Ctrl 说话")


def main():
    """主程序入口与界面生命周期调度"""
    app = QApplication(sys.argv)
    app.setWindowIcon(make_svg_icon(SVGS["cat"], 32))
    font = QFont()
    font.setFamilies(["SF Pro Text", "SF Pro Display", "PingFang SC", "Microsoft YaHei UI", "Segoe UI"])
    font.setPixelSize(12)
    app.setFont(font)
    app.setQuitOnLastWindowClosed(False)

    win = QWidget()
    win.setWindowTitle("Kypetz")
    win.setWindowIcon(make_svg_icon(SVGS["cat"], 32))
    win.setWindowFlags(
        Qt.WindowType.FramelessWindowHint |
        Qt.WindowType.WindowStaysOnTopHint |
        Qt.WindowType.Tool
    )
    win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    win.setFixedSize(WM_W, WM_H)

    root = QVBoxLayout(win)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    # 1. 顶部 Apple 药丸手柄
    handle = AppleDragHandle(win)
    root.addWidget(handle)

    # 2. Live2D WebEngine 视图
    view = QWebEngineView(win)
    view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    view.page().setBackgroundColor(QColor(0, 0, 0, 0))
    root.addWidget(view, 1)

    # 3. Apple 悬浮磨砂控制底座
    bar = AppleControlBar(win)
    bl = QHBoxLayout(bar)
    bl.setContentsMargins(20, 2, 20, 4)
    bl.setSpacing(8)

    btn_qss = """
        QPushButton {
          background: rgba(255, 255, 255, 0.08);
          color: rgba(255, 255, 255, 0.90);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 14px;
          font-size: 13px;
          font-weight: 500;
        }
        QPushButton:hover {
          background: rgba(255, 255, 255, 0.16);
          color: #FFFFFF;
          border: 1px solid rgba(255, 255, 255, 0.22);
        }
        QPushButton:pressed {
          background: rgba(255, 255, 255, 0.04);
        }
    """

    btnSettings = QPushButton("", bar)
    btnSettings.setFixedSize(30, 28)
    btnSettings.setIcon(make_svg_icon(SVGS["settings"], 15))
    btnSettings.setToolTip("控制中心 (模型/人设/日志/更新)")
    btnSettings.setStyleSheet(btn_qss)

    btnMsg = QPushButton("", bar)
    btnMsg.setFixedSize(30, 28)
    btnMsg.setIcon(make_svg_icon(SVGS["chat"], 15))
    btnMsg.setToolTip("键入文字")
    btnMsg.setStyleSheet(btn_qss)

    btnPlus = QPushButton("+", bar)
    btnPlus.setFixedSize(28, 28)
    btnPlus.setToolTip("放大角色 (支持鼠标滚轮放大)")
    btnPlus.setStyleSheet(btn_qss)

    btnMinus = QPushButton("−", bar)
    btnMinus.setFixedSize(28, 28)
    btnMinus.setToolTip("缩小角色 (支持鼠标滚轮缩小)")
    btnMinus.setStyleSheet(btn_qss)

    btnReset = QPushButton("1:1", bar)
    btnReset.setFixedSize(32, 28)
    btnReset.setToolTip("恢复原始 100% 居中大小")
    btnReset.setStyleSheet(btn_qss)

    btnExit = QPushButton("", bar)
    btnExit.setFixedSize(30, 28)
    btnExit.setIcon(make_svg_icon(SVGS["power"], 14, stroke_color="#FF453A"))
    btnExit.setToolTip("退出 Kypetz (快捷键 Ctrl+Shift+Q)")
    btnExit.setStyleSheet("""
        QPushButton {
            background: rgba(255, 69, 58, 0.16);
            color: #FF453A;
            border: 1px solid rgba(255, 69, 58, 0.28);
            border-radius: 14px;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton:hover {
            background: rgba(255, 69, 58, 0.35);
            color: #ffffff;
            border: 1px solid rgba(255, 69, 58, 0.5);
        }
    """)
    btnExit.clicked.connect(app.quit)

    status = QLabel("按住 Ctrl 说话", bar)
    status.setStyleSheet(
        "color: rgba(255, 255, 255, 0.70); font-size: 11.5px; font-weight: 400; padding: 0 4px;"
    )

    bl.addWidget(btnSettings)
    bl.addWidget(btnMsg)
    bl.addWidget(btnPlus)
    bl.addWidget(btnMinus)
    bl.addWidget(btnReset)
    bl.addWidget(btnExit)
    bl.addStretch(1)
    bl.addWidget(status)
    root.addWidget(bar)

    # 缩放与打字抽屉交互绑定
    btnPlus.clicked.connect(lambda: win.bridge.eval_js.emit("window.setRanaScale && window.setRanaScale(1.12)"))
    btnMinus.clicked.connect(lambda: win.bridge.eval_js.emit("window.setRanaScale && window.setRanaScale(0.89)"))
    btnReset.clicked.connect(lambda: win.bridge.eval_js.emit("window.resetRanaScale && window.resetRanaScale()"))
    btnMsg.clicked.connect(lambda: win.bridge.eval_js.emit("window.toggleInput && window.toggleInput()"))

    # 通信桥接
    win.bridge = JsBridge(view)

    def _on_show_user(text):
        user_call = _cfg.get("user_call", "你").strip() or "你"
        win.bridge.eval_js.emit(
            f"window.showUserBubble && window.showUserBubble({json.dumps(text, ensure_ascii=False)}, {json.dumps(user_call, ensure_ascii=False)})"
        )

    def _on_show_reply(reply, dur_ms):
        pet_name = _cfg.get("pet_name", "桌宠").strip() or "桌宠"
        win.bridge.eval_js.emit(
            f"window.showRanaBubble && window.showRanaBubble({json.dumps(reply, ensure_ascii=False)}, {dur_ms}, {json.dumps(pet_name, ensure_ascii=False)})"
        )
        win.bridge.eval_js.emit(
            f"window.onExternalReply && window.onExternalReply({json.dumps(reply, ensure_ascii=False)}, {dur_ms})"
        )

    _ui_sig.show_user.connect(_on_show_user)
    _ui_sig.show_reply.connect(_on_show_reply)
    _ui_sig.trigger_action.connect(
        lambda mot, exp, dur: win.bridge.eval_js.emit(
            f"window.performAction && window.performAction('{mot}', '{exp}', {dur})"
        )
    )
    _ui_sig.status.connect(status.setText)

    # QWebChannel 桥接注册
    win.channel = QWebChannel(view.page())
    view.page().setWebChannel(win.channel)
    win.move_obj = MoveObj(win)
    win.channel.registerObject("bridge", win.move_obj)

    cur_model = _cfg.get("live2d_model", "")
    if not cur_model:
        from ui.dashboard import scan_available_models
        discovered = scan_available_models()
        cur_model = discovered[0]["key"] if discovered else "038_collabo_a_ur" 
    view.load(QUrl(f"http://127.0.0.1:{PORT}/Live2D/index.html?nochat=1&v=5&model={cur_model}"))

    timer = QTimer(win)
    timer.timeout.connect(lambda: _drain(result_queue, win.bridge))
    timer.start(200)

    # 屏幕全域视线灵动追踪 (彻底突破窗口边框，全局眼神与头部跟随鼠标)
    last_mouse_pos = [-9999, -9999]
    def track_global_cursor():
        try:
            pos = QCursor.pos()
            mx, my = pos.x(), pos.y()
            if abs(mx - last_mouse_pos[0]) > 2 or abs(my - last_mouse_pos[1]) > 2:
                last_mouse_pos[0], last_mouse_pos[1] = mx, my
                rel_x = mx - win.x()
                rel_y = my - win.y()
                win.bridge.eval_js.emit(f"window.focusGlobal && window.focusGlobal({rel_x}, {rel_y})")
        except Exception:
            pass

    cursor_timer = QTimer(win)
    cursor_timer.timeout.connect(track_global_cursor)
    cursor_timer.start(45)

    def on_change_skin(skin_key):
        win.bridge.eval_js.emit(f"window.changeModel && window.changeModel('{skin_key}')")

    # 控制中枢实例 (提前初始化，提升点击响应速度并支持置顶激活)
    dashboard = KypetzDashboard(
        cfg=_cfg,
        save_cb=save_config,
        fetch_cb=fetch_models,
        change_skin_cb=on_change_skin,
        parent=win
    )

    def show_dashboard():
        try:
            dashboard.show()
            dashboard.raise_()
            dashboard.activateWindow()
        except Exception as e:
            print("[Dashboard open err]", e)

    btnSettings.clicked.connect(show_dashboard)

    # 快捷键事件监听 (全面支持 left ctrl / right ctrl 以及防 auto-repeat 抖动)
    def on_key_event(e):
        key_name = (e.name or "").lower()
        if "ctrl" in key_name:
            if e.event_type == "down":
                if not _recording[0] and not _is_speaking.is_set():
                    _recording[0] = True
                    _last_user_activity[0] = time.time()
                    play_chime(CHIME_START)
                    _ui_sig.status.emit("正在聆听… (松开结束)")
                    print("[ASR] 麦克风录音开始...")
                    threading.Thread(
                        target=lambda: result_queue.put(record_and_recognize()),
                        daemon=True
                    ).start()
            elif e.event_type == "up":
                if _recording[0]:
                    _recording[0] = False
                    _ui_sig.status.emit("正在识别语音…")
                    print("[ASR] 麦克风录音结束，送入识别流水线...")

    try:
        keyboard.hook(on_key_event)
        keyboard.add_hotkey("ctrl+shift+q", app.quit)
    except Exception as e:
        print("[Keyboard Hook err]", e)

    # 启动后台守护服务与线程
    ensure_server(PORT)
    warmup_sovits()
    threading.Thread(target=idle_companion_loop, args=(win,), daemon=True).start()

    # 居中贴近屏幕右下角展示
    screen = QApplication.primaryScreen().geometry()
    win.move(screen.width() - WM_W - 40, screen.height() - WM_H - 80)
    win.show()

    # 标准输出流重定向至控制中心
    sys.stdout = StdoutRedirector(sys.__stdout__, _log_emitter.log_signal)
    sys.stderr = StdoutRedirector(sys.__stderr__, _log_emitter.log_signal)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
