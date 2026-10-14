# -*- coding: utf-8 -*-
"""
Kypetz 物理音频提示音模块
使用数学正弦波实时合成按键交互音效，零磁盘残留。
"""

import threading
import numpy as np
import sounddevice as sd


def _gen_tone(freqs, duration=0.10, sr=24000) -> np.ndarray:
    """生成带平滑包络的正弦提示音"""
    t = np.linspace(0, duration, int(sr * duration), False)
    wave = np.zeros_like(t)
    for f in freqs:
        wave += np.sin(2 * np.pi * f * t)
    wave /= max(1, len(freqs))
    env = np.sin(np.pi * t / duration) ** 2
    return (wave * env * 0.28).astype(np.float32)


CHIME_START = _gen_tone([523.25, 659.25], 0.08)       # C5 + E5: 麦克风开启
CHIME_SENT = _gen_tone([587.33, 880.00], 0.12)        # D5 + A5: 消息发送成功
CHIME_MISS = _gen_tone([329.63, 293.66], 0.15)        # 失败或未识别


def play_chime(tone: np.ndarray) -> None:
    """异步非阻塞播放提示音"""
    def _p():
        try:
            sd.play(tone, samplerate=24000)
            sd.wait()
        except Exception:
            pass

    threading.Thread(target=_p, daemon=True).start()
