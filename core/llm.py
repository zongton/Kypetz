# -*- coding: utf-8 -*-
"""
Kypetz 大语言模型与翻译接口模块
兼容 OpenAI 规范的 Chat Completions API 调用、模型清单动态拉取及 SoVITS 日语本地化翻译。
"""

import json
import re
import urllib.request
from core.config import _cfg, get_dynamic_prompt


def llm_ask(text: str) -> str:
    """
    请求配置的大语言模型进行对话。
    若未配置 API 或请求异常，则平滑降级至本地二次元规则库。
    """
    base = _cfg.get("llm_base", "").strip()
    key = _cfg.get("llm_key", "").strip()
    model = _cfg.get("llm_model", "").strip()
    system_content = get_dynamic_prompt(_cfg.get("live2d_model", ""))

    if base:
        try:
            url = base.rstrip("/") + "/chat/completions"
            body = json.dumps({
                "model": model or "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": text},
                ],
                "max_tokens": 120,
                "temperature": 0.9,
            }).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if key:
                headers["Authorization"] = "Bearer " + key
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                content = ((json.load(r)["choices"][0]["message"].get("content") or "") or "").strip()
            if not content:
                # 针对极端极简模型的重试兜底
                try:
                    body2 = json.dumps({
                        "model": model or "gpt-4o-mini",
                        "messages": [{"role": "user", "content": "用一句极简短的中文回答: " + text}],
                        "max_tokens": 80,
                    }).encode("utf-8")
                    req2 = urllib.request.Request(url, data=body2, headers=headers)
                    with urllib.request.urlopen(req2, timeout=60) as r2:
                        content = ((json.load(r2)["choices"][0]["message"].get("content") or "") or "").strip()
                except Exception:
                    content = ""
            return content if content else "……嗯。"
        except Exception as e:
            print("[LLM]", e)
            return "……连接中断了。请在控制面板检查 API 配置。"

    # 本地离线规则降级兜底
    rules = [
        (r"你好|嗨|hi|在吗", "你好呀，很高兴见到你！"),
        (r"可爱|喜欢", "嘿嘿，谢谢你的夸奖～"),
        (r"难过|累|压力|烦", "工作辛苦啦，深呼吸放松一下吧。"),
        (r"再见|拜拜|晚安", "晚安，明天见哦！"),
    ]
    for pat, ans in rules:
        if re.search(pat, text, re.I):
            return ans
    return "……（默默看着你）"


def fetch_models(base: str, key: str) -> list:
    """拉取服务端支持的模型列表 ID"""
    if not base:
        return []
    url = base.rstrip("/") + "/models"
    headers = {}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    return [m["id"] for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]


def translate_to_ja(text: str) -> str:
    """
    将中文台词翻译为自然口语日语，专供 SoVITS 语音合成。
    若未配置 LLM 或翻译失败，则返回原文本降级。
    """
    if not text:
        return ""
    # 若已经包含日文假名，视为日文无需重复翻译
    if len(re.findall(r"[぀-ゟ゠-ヿ]", text)) >= 2:
        return text

    base = _cfg.get("llm_base", "").strip()
    key = _cfg.get("llm_key", "").strip()
    model = _cfg.get("llm_model", "").strip()
    if not base:
        return text

    try:
        url = base.rstrip("/") + "/chat/completions"
        prompt = (
            "你是一个专业的二次元动漫本地化翻译器。请将以下简短的中文角色台词翻译为符合少女语气、自然地道的日常口语日语。"
            "只输出翻译后的纯日文，绝不要包含任何解释、假名注音、动作描写或引号。"
        )
        body = json.dumps({
            "model": model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            "max_tokens": 100,
            "temperature": 0.3,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as r:
            res = json.load(r)
            ja = ((res["choices"][0]["message"].get("content") or "")).strip()
            # 过滤多余引号与空白
            for ch in ['"', "'", "“", "”", "「", "」", "\n", "\r"]:
                ja = ja.replace(ch, "")
            return ja.strip() if ja.strip() else text
    except Exception as e:
        print("[TTS][Translate JA Fail]", e)
        return text

def llm_ask_proactive(pet_name: str = "桌宠", user_call: str = "主人", model_key: str = None) -> str:
    """
    当用户挂机空闲时，主动唤醒大模型进行自主思考并挑起话题。
    """
    base = _cfg.get("llm_base", "").strip()
    if not base:
        # 本地离线通用挂机话题降级
        fallbacks = [
            f"……{user_call}，在忙什么呢？",
            f"……发呆中。要不要起来喝杯水？",
            f"……一直看着屏幕，眼睛不酸吗？",
            f"……今天好像有点安静呢。",
            f"……（轻轻伸了个懒腰）",
        ]
        import random
        return random.choice(fallbacks)

    prompt = (
        f"(现在四周很安静，你在桌面上已经静静看着{user_call}好一会儿了。"
        f"请完全代入你的性格与口吻，主动打破沉默对{user_call}说一句简短自然的话——"
        f"可以是一个新鲜奇特的小想法、一句关心的轻声问候、随性的小吐槽或者软萌的自言自语。"
        f"必须在句首配合一个动作标签如 [action: 动作名]，中文30字以内，自由发挥，禁止输出模板化套话。)"
    )
    return llm_ask(prompt)
