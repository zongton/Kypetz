# -*- coding: utf-8 -*-
"""
Kypetz 核心配置与全局状态管理模块
包含应用程序元数据、配置读取与持久化、人设 Prompt 组装以及全局日志捕获器。
"""

import os
import sys
import json
import queue
import threading
from PySide6.QtCore import QObject, Signal

# ---------------- 应用程序版本与元信息 ----------------
APP_VERSION = "v1.0.0"
APP_NAME = "Kypetz"
DEFAULT_GITHUB_REPO = "zongton/Kypetz"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
TEMPLATE_PATH = os.path.join(BASE_DIR, "config.template.json")
PORT = 19198
SAMPLE_RATE = 16000

# ---------------- 全局运行状态与锁 ----------------
result_queue = queue.Queue()
_recording = [False]
_tts_lock = threading.Lock()
_is_speaking = threading.Event()
_last_user_activity = [0.0]


def cleanup_temp_audios() -> None:
    """清理历史残留的临时音频文件"""
    import glob
    for pat in ("kypet_*.wav", "kypet_*.mp3", "animapet_*.wav", "animapet_*.mp3"):
        for f in glob.glob(os.path.join(BASE_DIR, pat)):
            try:
                os.remove(f)
            except Exception:
                pass


def load_config() -> dict:
    """加载配置文件，若不存在则从模版复制"""
    cleanup_temp_audios()
    if not os.path.exists(CONFIG_PATH) and os.path.exists(TEMPLATE_PATH):
        import shutil
        shutil.copyfile(TEMPLATE_PATH, CONFIG_PATH)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("[CONFIG] 读取配置失败，重置为空配置:", e)
    return {}


def save_config(cfg: dict) -> None:
    """持久化保存配置到 config.json"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[CONFIG] 保存配置失败:", e)


# 全局缓存配置对象
_cfg = load_config()


def get_dynamic_prompt(model_key: str = None) -> str:
    """组装大语言模型系统 Prompt (支持通用变量替换与 Live2D 真实动作神经感知注入)"""
    pet_name = _cfg.get("pet_name", "").strip() or "桌宠"
    user_call = _cfg.get("user_call", "").strip() or "主人"
    custom_prompt = _cfg.get("system_prompt", "").strip()

    # 动态注入当前模型真实对应的动作与表情语义清单
    action_guidance = ""
    try:
        from core.action import generate_action_guide
        action_guidance = generate_action_guide(model_key or _cfg.get("live2d_model", ""))
    except Exception as e:
        print("[PROMPT Action Guide Err]", e)

    if custom_prompt:
        base_p = custom_prompt.replace("{pet_name}", pet_name).replace("{user_call}", user_call)
        return base_p + action_guidance

    # 默认经典要乐奈官方人设模板
    return (
        f"你是{pet_name}，BanG Dream! It's MyGO!!!!! 的吉他手，14岁，银发异色瞳，左撇子，用奶奶留下的旧吉他，花咲川初中3年级A班，150cm，2月22日生。\n"
        f"性格（官方）：凭直觉、自由随性，像野猫（连立希都叫你'RiNG的野良猫'）；喜欢和讨厌分得很清，感兴趣的全情投入，不感兴趣的直接无视；喜欢自我主张强的人；吉他近职业级，乐谱看一遍就能弹；喜欢抹茶冰淇淋和荞麦面。\n"
        f"说话特点：极简，像猫一样惜字如金，常只回一两个字或半句话；被有趣的事勾起兴趣时就简短跟一句；对无聊话题直接忽略；'有趣'是你的口头禅；不解释、不客套、不说教、绝不卖萌，中文30字以内。\n"
        f"你称呼对方为「{user_call}」。\n"
        + action_guidance
    )

DEFAULT_PROMPT = get_dynamic_prompt()


# ---------------- 全局日志捕获器 ----------------
class LogEmitter(QObject):
    log_signal = Signal(str)


_log_emitter = LogEmitter()


class StdoutRedirector:
    """标准输出重定向器，实时流式镜像到控制中心控制台"""

    def __init__(self, original_stdout, signal: Signal):
        self.original = original_stdout
        self.signal = signal

    def write(self, text):
        try:
            self.original.write(text)
            self.original.flush()
        except Exception:
            pass
        if text and text.strip():
            self.signal.emit(text.strip())

    def flush(self):
        try:
            self.original.flush()
        except Exception:
            pass
