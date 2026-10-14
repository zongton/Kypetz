# -*- coding: utf-8 -*-
"""
Kypetz 语音合成服务 (TTS) 调度模块
支持 GPT-SoVITS 深度定制声线（中/日双语模式）与微软 Edge-TTS 零显卡轻量兜底。
"""

import os
import re
import tempfile
import threading
import urllib.request
import urllib.parse
from core.config import _cfg, _tts_lock
from core.llm import translate_to_ja
from audio.player import _play_audio_clean, _ui_sig


def warmup_sovits() -> None:
    """开机预热 SoVITS 端口，避免首次对话因模型冷加载产生卡顿"""
    tts_url = _cfg.get("tts_url", "").strip()
    if not tts_url:
        return

    def _warm():
        try:
            params = {
                "refer_wav_path": _cfg.get("ref_wav", "").strip(),
                "prompt_text": _cfg.get("prompt_text", "").strip(),
                "prompt_language": _cfg.get("prompt_lang", "zh"),
                "text": "嗯。",
                "text_language": "zh",
                "top_k": 20,
                "top_p": 0.6,
                "temperature": 0.6,
            }
            url = tts_url.rstrip("/") + "/?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=12) as r:
                r.read(1024)
            print("[SoVITS] 预热完毕，随时待命 ✓")
        except Exception:
            pass

    threading.Thread(target=_warm, daemon=True).start()


def clean_for_sovits(text: str, lang: str = "zh") -> str:
    """清洗供 SoVITS 发音的台词文本，避免念出舞台括号与分词崩溃符号"""
    t = text or ""
    # 1. 过滤掉舞台动作括号，避免模型念出括号音
    t = re.sub(r"[（\(【\[][^）\)】\]]*[）\)】\]]", "", t)
    if lang == "zh":
        # 2. 中文模式：通用科技与日常英文音译 (防止 SoVITS 英文分词器崩溃导致报错与电流音)
        t = re.sub(r"(?i)live", "演出", t)
        t = re.sub(r"(?i)band", "乐队", t)
        t = re.sub(r"(?i)ok", "好的", t)
        t = re.sub(r"(?i)bye", "拜拜", t)
        t = re.sub(r"(?i)hi|hello", "你好", t)
        t = re.sub(r"(?i)gpt", "模型", t)
        t = re.sub(r"(?i)ai", "智能", t)
        t = re.sub(r"[a-zA-Z]+", "", t)
    # 3. 过滤特殊符号，保留日文字符及标点
    t = re.sub(r"[*#~`_『』「」【】]+", "", t).strip()
    return t if t else "……"


def speak(user: str, reply: str, voice_text: str, mot: str = None, exp: str = None) -> None:
    """启动独立线程调度语音合成流水线"""
    threading.Thread(target=_speak_worker, args=(user, reply, voice_text, mot, exp), daemon=True).start()


def _speak_worker(user: str, reply: str, voice_text: str, mot: str = None, exp: str = None) -> None:
    """语音合成核心工作流"""
    with _tts_lock:
        tts_url = _cfg.get("tts_url", "").strip()
        voice_lang = _cfg.get("voice_lang", "zh").strip()

        # 根据配置决定语音合成语言
        actual_lang = "zh"
        raw_speech = voice_text or reply
        if voice_lang == "ja" and tts_url:
            actual_lang = "ja"
            translated = translate_to_ja(raw_speech)
            sovits_text = clean_for_sovits(translated, lang="ja")
            print(f"[TTS][JA] 中文台词: '{raw_speech}' -> 日语发音: '{sovits_text}'")
        else:
            sovits_text = clean_for_sovits(raw_speech, lang="zh")

        # 优先使用 GPT-SoVITS
        if tts_url and sovits_text:
            try:
                params = {
                    "refer_wav_path": _cfg.get("ref_wav", "").strip(),
                    "prompt_text": _cfg.get("prompt_text", "").strip(),
                    "prompt_language": _cfg.get("prompt_lang", "zh"),
                    "text": sovits_text,
                    "text_language": actual_lang,
                    "top_k": 20,
                    "top_p": 0.6,
                    "temperature": 0.6,
                }
                url = tts_url.rstrip("/") + "/?" + urllib.parse.urlencode(params)
                with urllib.request.urlopen(url, timeout=300) as r:
                    raw_audio = r.read()

                # 专业无杂音纯内存播放 (reply 保持原始中文，保证界面字幕始终为中文！)
                _play_audio_clean(raw_audio, reply, mot, exp)
                return
            except Exception as e:
                print("[TTS][fallback edge]", e)

        # 降级使用微软 Edge-TTS (纯内存自清除)
        mp3 = None
        wav = None
        try:
            import asyncio
            import edge_tts
            import subprocess
            mp3 = os.path.join(tempfile.gettempdir(), f"kypetz_say_{os.urandom(4).hex()}.mp3")
            asyncio.new_event_loop().run_until_complete(
                edge_tts.Communicate(sovits_text, _cfg.get("tts_voice", "zh-CN-XiaoyiNeural")).save(mp3)
            )
            wav = mp3[:-4] + ".wav"
            subprocess.run(
                ["ffmpeg", "-y", "-i", mp3, "-ar", "44100", "-ac", "2", wav],
                capture_output=True, timeout=30
            )
            with open(wav, "rb") as f:
                raw_audio = f.read()

            _play_audio_clean(raw_audio, reply, mot, exp)
        except Exception as e:
            print("[TTS]", e)
            _ui_sig.show_reply.emit(reply, 3000)
            _ui_sig.status.emit("按住 Ctrl 说话")
        finally:
            for fpath in (mp3, wav):
                if fpath and os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
