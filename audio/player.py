import re
# -*- coding: utf-8 -*-
"""
Kypetz 纯内存零磁盘残留音频播放引擎
支持 44.1kHz 专业 sinc 重采样、双声道立体声平衡、淡入淡出爆音消除以及音画动作毫秒级同步。
"""

import io
import wave
import numpy as np
import scipy.signal
import sounddevice as sd
from PySide6.QtCore import QObject, Signal
from core.config import _is_speaking


class _UISig(QObject):
    show_user = Signal(str)
    show_reply = Signal(str, int)            # 文本, 音频时长ms (用于绝对音画同步)
    trigger_action = Signal(str, str, int)  # mot, exp, dur_ms (身体动作与表情触发)
    status = Signal(str)


_ui_sig = _UISig()


def _play_audio_clean(raw_wav_bytes: bytes, reply: str, mot: str = None, exp: str = None) -> None:
    """
    高保真纯内存播放音频流。
    在启动声卡硬件发声的同一瞬间，发射字幕卡片弹出与 Live2D 身体动作触发信号。
    """
    wf = wave.open(io.BytesIO(raw_wav_bytes))
    sr = wf.getframerate()
    data_int16 = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    wf.close()

    # 1. 转换为 32 位浮点音频 [-1.0, 1.0]，杜绝整型量化溢出杂音
    data_float = data_int16.astype(np.float32) / 32768.0

    # 2. 高质量傅里叶 sinc 重采样到声卡硬件标准 44100Hz (彻底根除 32000Hz 在 Windows MME 驱动下的高频电流声)
    TARGET_SR = 44100
    if sr != TARGET_SR:
        num_samples = int(len(data_float) * TARGET_SR / sr)
        data_float = scipy.signal.resample(data_float, num_samples).astype(np.float32)

    # 3. 严格转换为立体声双声道 (L+R)，解决单声道相位失衡引起的电杂音
    stereo = np.column_stack((data_float, data_float))

    # 4. 头部与尾部 10ms 平滑淡入淡出包络，杜绝 DAC 瞬态开关电爆音
    fade = min(441, len(stereo))
    stereo[:fade] *= np.linspace(0, 1, fade)[:, None]
    stereo[-fade:] *= np.linspace(1, 0, fade)[:, None]

    dur_ms = int(len(stereo) / TARGET_SR * 1000)

    # 绝对音画同步：在开始播放声音的同一瞬间弹出文字卡片、启动口型并同步触发肢体动作！
    # 剥离机器指令标签，仅在卡片上展示干净自然台词
    display_text = re.sub(r"\[(?:action|motion|expression)\s*:[^\]]*\]", "", reply).strip()
    _ui_sig.show_reply.emit(display_text if display_text else reply, dur_ms)
    if mot or exp:
        _ui_sig.trigger_action.emit(mot or "", exp or "", dur_ms)

    _is_speaking.set()  # 开启防打断锁定
    try:
        sd.play(stereo, samplerate=TARGET_SR)
        sd.wait()
    finally:
        _is_speaking.clear()
        _ui_sig.status.emit("按住 Ctrl 说话")
