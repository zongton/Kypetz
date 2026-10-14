# -*- coding: utf-8 -*-
"""
Kypetz 离线语音识别 (ASR) 模块
基于 Vosk 轻量级离线识别引擎，集成模型热检测、麦克风自适应动态音量增益 (AGC) 与多片段拼装算法。
"""

import os
import time
import json
import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer
from PySide6.QtCore import QTimer
from core.config import BASE_DIR, SAMPLE_RATE, _recording, _last_user_activity
from audio.chimes import play_chime, CHIME_START, CHIME_SENT, CHIME_MISS
from audio.player import _ui_sig


def find_vosk_model() -> str:
    """自动扫描与定位本地 Vosk 离线模型目录"""
    candidates = [
        os.path.join(BASE_DIR, "models", "vosk-model-small-cn-0.22"),
        os.path.join(BASE_DIR, "vosk-model-small-cn-0.22"),
        os.path.join(BASE_DIR, "models"),
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.isdir(c):
            # 确认包含 am/或 model 文件的目录
            if any(f in os.listdir(c) for f in ["am", "conf", "README", "model"]):
                return c

    # 全局模糊递归扫描
    for d in [os.path.join(BASE_DIR, "models"), BASE_DIR]:
        if os.path.exists(d):
            for sub in os.listdir(d):
                sub_p = os.path.join(d, sub)
                if sub.startswith("vosk-model") and os.path.isdir(sub_p):
                    return sub_p
    return ""


_model = None


def get_or_load_model():
    """获取或动态延迟热加载 Vosk 模型"""
    global _model
    if _model is not None:
        return _model
    model_path = find_vosk_model()
    if model_path:
        try:
            print(f"[ASR] 正在加载 Vosk 离线模型: {model_path} ...")
            _model = Model(model_path)
            print(f"[ASR] Vosk 离线语音识别模型加载就绪 ✓")
        except Exception as e:
            print("[ASR] Vosk 模型初始化失败:", e)
    return _model


# 启动时首次预加载
get_or_load_model()


def record_and_recognize() -> str:
    """监听麦克风并进行离线高灵敏度语音识别"""
    _last_user_activity[0] = time.time()
    current_model = get_or_load_model()
    if not current_model:
        play_chime(CHIME_MISS)
        _ui_sig.status.emit("未检测到 Vosk 模型 (请放入 models/ 目录)")
        print("[ASR] 未检测到离线语音识别模型！请下载 vosk-model-small-cn-0.22 解压并放入 models/ 文件夹下。")
        QTimer.singleShot(2500, lambda: _ui_sig.status.emit("按住 Ctrl 说话"))
        return ""

    try:
        rec = KaldiRecognizer(current_model, SAMPLE_RATE)
        rec.SetWords(False)
    except Exception as e:
        print("[ASR] KaldiRecognizer 构建失败:", e)
        return ""

    frames = []

    def cb(indata, frames_, t, status):
        frames.append(bytes(indata))

    try:
        import keyboard
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
            callback=cb, blocksize=1600
        ):
            while _recording[0]:
                # 物理按键状态主动自省双重保险：即便系统丢掉 KeyUp 钩子，松手也立刻安全终止
                try:
                    if not keyboard.is_pressed("ctrl"):
                        _recording[0] = False
                        break
                except Exception:
                    pass
                time.sleep(0.03)
    except Exception as e:
        print("[ASR] 麦克风录音设备调用失败:", e)
        _ui_sig.status.emit("麦克风设备异常")
        QTimer.singleShot(2000, lambda: _ui_sig.status.emit("按住 Ctrl 说话"))
        return ""

    data = b"".join(frames)
    if len(data) < SAMPLE_RATE * 0.35:  # 小于 0.35 秒忽略
        play_chime(CHIME_MISS)
        _ui_sig.status.emit("说话时间过短")
        QTimer.singleShot(1500, lambda: _ui_sig.status.emit("按住 Ctrl 说话"))
        return ""

    # 音频自适应动态增益 (AGC)：麦克风音量偏小是 Vosk 漏词的主要原因
    try:
        audio_int16 = np.frombuffer(data, dtype=np.int16)
        max_val = float(np.max(np.abs(audio_int16)))
        if max_val > 60:
            gain = min(8.0, 26000.0 / max(1.0, max_val))
            boosted = np.clip(audio_int16 * gain, -32767, 32767).astype(np.int16)
            data = boosted.tobytes()
    except Exception as e:
        print("[ASR AGC err]", e)

    # 完整拼接所有分块识别结果
    parts = []
    for i in range(0, len(data), 4000):
        chunk = data[i:i + 4000]
        if rec.AcceptWaveform(chunk):
            r = json.loads(rec.Result())
            if r.get("text"):
                parts.append(r["text"])
    fin = json.loads(rec.FinalResult())
    if fin.get("text"):
        parts.append(fin["text"])

    _recording[0] = False
    text = "".join(parts).replace(" ", "").strip()
    if text:
        print(f"[ASR] 离线识别成功: '{text}'")
        play_chime(CHIME_SENT)
        _ui_sig.show_user.emit(text)
        _ui_sig.status.emit("已发送 ✨")
    else:
        print("[ASR] 未能识别出有效语音文本")
        play_chime(CHIME_MISS)
        _ui_sig.status.emit("未识别到清晰语音")
        QTimer.singleShot(1500, lambda: _ui_sig.status.emit("按住 Ctrl 说话"))
    return text
