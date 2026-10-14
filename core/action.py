# -*- coding: utf-8 -*-
"""
Kypetz 通用动作语义解析与 Live2D 动态指令模块
1. 动态自省当前 Live2D 模型实际具备的动作 (Motions) 与表情 (Expressions) 元数据；
2. 支持大模型使用指令协议 [action: 动作名, 表情名] 直接控制模型；
3. 支持自然语言动作描述向当前模型可用动作集的语义自适应匹配。
"""

import os
import re
import json
import random
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------- 通用动作意图词根索引 (跨角色自适应) ----------------
# 任意 Live2D 模型只要动作名或表情名包含以下常用英文/拼音词根，即可全自动对齐
UNIVERSAL_INTENT_ROOTS = [
    (["笑", "微笑", "开心", "好", "点头", "赞", "高兴", "满意"], ["smile", "happy", "joy", "nod", "laugh", "glee", "nf01", "nf03"]),
    (["歪头", "思考", "想", "疑惑", "不解", "为什么", "侧头", "打量"], ["thinking", "think", "wonder", "doubt", "curious", "tilt", "nf02", "nf04"]),
    (["脸红", "害羞", "羞", "别过头", "扭过头", "傲娇", "娇", "笨蛋"], ["shame", "shy", "blush", "embarrass"]),
    (["坏笑", "猫笑", "猫", "喵", "得意", "狡黠", "调皮", "恶作剧"], ["niya", "smirk", "mischief", "cat", "proud"]),
    (["生气", "鼓嘴", "怒", "瞪", "气", "可恶", "烦", "哼", "讨厌"], ["angry", "rage", "pout", "furious", "mad"]),
    (["叹气", "哈欠", "累", "困", "睡觉", "无聊", "趴", "休息"], ["sigh", "yawn", "sleep", "tired", "bored", "idle"]),
    (["认真", "严肃", "凝视", "盯", "注视", "专注", "仔细"], ["serious", "focus", "stare", "gaze", "kime"]),
    (["惊讶", "哇", "愣", "呆", "吓", "睁大", "不会吧"], ["surprised", "surprise", "shock", "gasp", "wide"]),
    (["再见", "拜拜", "挥手", "晚安", "走", "下次见", "告别"], ["bye", "wave", "farewell", "leave"]),
    (["难过", "哭", "委屈", "流泪", "伤心", "悲伤", "啜泣"], ["cry", "sad", "tear", "grief"]),
]


def get_model_capabilities(model_key: str = None) -> tuple:
    """
    动态自省指定或当前配置的 Live2D 模型目录，
    解析其 index.json 或 model.json，返回实际可用的 (motions_list, expressions_list)。
    """
    key = model_key
    if not key:
        try:
            from core.config import _cfg
            key = _cfg.get("live2d_model", "")
        except Exception:
            cfg_p = os.path.join(BASE_DIR, "config.json")
            if os.path.exists(cfg_p):
                try:
                    with open(cfg_p, "r", encoding="utf-8") as file:
                        key = json.load(file).get("live2d_model", "")
                except Exception:
                    key = "" 
    full_path = None

    if key:
        # 支持绝对路径与各种相对路径组合
        candidates = [
            os.path.join(BASE_DIR, "Live2D", key),
            os.path.join(BASE_DIR, "Live2D", "live2d-model", key),
            os.path.join(BASE_DIR, key),
            key if os.path.isabs(key) else os.path.join(BASE_DIR, key),
        ]
        for c in candidates:
            if os.path.exists(c) and os.path.isdir(c):
                full_path = c
                break

    # 若未找到则全局扫描 Live2D/live2d-model 下的第一个可用模型作为降级
    if not full_path:
        model_root = os.path.join(BASE_DIR, "Live2D", "live2d-model")
        if os.path.exists(model_root):
            for r, dirs, files in os.walk(model_root):
                if any(f in files for f in ["index.json", "model.json"]):
                    full_path = r
                    break

    if not full_path:
        return [], []

    meta = None
    for f in ["index.json", "model.json"]:
        p = os.path.join(full_path, f)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as file:
                    meta = json.load(file)
                break
            except Exception:
                pass

    if not meta:
        return [], []

    motions = list(meta.get("motions", {}).keys())
    expressions = [
        e.get("name") for e in meta.get("expressions", [])
        if isinstance(e, dict) and e.get("name")
    ]
    return motions, expressions


def parse_ai_action(reply_text: str, available_motions: list = None, available_expressions: list = None) -> tuple:
    """
    从大模型回复中提取动作与表情控制指令。
    优先级：
    1. 显式指令标签协议：[action: motion, expression] 或 [motion: mot] 或 [expression: exp]
    2. 舞台动作括号描述：依据词根模糊匹配当前模型支持的可用动作
    3. 自然交谈兜底：从当前模型可用的 idle/talk 动作中动态选取
    """
    t = reply_text or ""
    if available_motions is None or available_expressions is None:
        m_list, e_list = get_model_capabilities()
        if available_motions is None:
            available_motions = m_list
        if available_expressions is None:
            available_expressions = e_list

    # --- 阶段 1: 显式指令标签协议解析 (最高自由度) ---
    # 格式支持: [action: motion] 或 [action: motion, exp]
    act_match = re.search(r"\[action\s*:\s*([a-zA-Z0-9_\-]+)(?:\s*,\s*([a-zA-Z0-9_\-]+))?\]", t, re.I)
    if act_match:
        target_mot = act_match.group(1).strip()
        target_exp = act_match.group(2).strip() if act_match.group(2) else None
        # 校验是否在模型支持的列表中 (不区分大小写模糊比对)
        mot_matched = _match_exact_or_case(target_mot, available_motions)
        exp_matched = _match_exact_or_case(target_exp, available_expressions) if target_exp else None
        if mot_matched or exp_matched:
            return mot_matched or target_mot, exp_matched or target_exp

    # 独立 [motion: ...] 或 [expression: ...] 标签
    mot_m = re.search(r"\[motion\s*:\s*([a-zA-Z0-9_\-]+)\]", t, re.I)
    exp_m = re.search(r"\[expression\s*:\s*([a-zA-Z0-9_\-]+)\]", t, re.I)
    if mot_m or exp_m:
        mot = _match_exact_or_case(mot_m.group(1).strip(), available_motions) if mot_m else None
        exp = _match_exact_or_case(exp_m.group(1).strip(), available_expressions) if exp_m else None
        return mot, exp

    # --- 阶段 2: 舞台圆括号动作描述语义自适应模糊匹配 ---
    brackets = re.findall(r"[（\(【\[\*](.*?)[）\)】\]\*]", t)
    search_scope = " ".join(brackets) if brackets else t

    for ch_keys, root_keys in UNIVERSAL_INTENT_ROOTS:
        if any(k in search_scope for k in ch_keys):
            # 在当前模型拥有的可用动作中寻找包含 root_keys 的动作
            matched_mot = _find_best_match(root_keys, available_motions)
            matched_exp = _find_best_match(root_keys, available_expressions)
            if matched_mot or matched_exp:
                return matched_mot, matched_exp

    # --- 阶段 3: 说话自然动作兜底 (优先使用含有 idle/nf/talk 的动作，绝不僵硬) ---
    fallback_mot = _find_best_match(["idle", "nf", "talk", "normal"], available_motions)
    if not fallback_mot and available_motions:
        fallback_mot = random.choice(available_motions)

    return fallback_mot, None


def strip_action_tags(text: str) -> str:
    """从大模型回复中彻底抹去指令标签与动作括号，输出纯净台词"""
    t = text or ""
    # 抹去 [action: ...] 等显式指令标签
    t = re.sub(r"\[(?:action|motion|expression)\s*:[^\]]*\]", "", t, flags=re.I)
    # 抹去各种形式的舞台动作括号
    t = re.sub(r"[（\(【\[\*][^）\)】\]\*]*[）\)】\]\*]", "", t)
    return t.strip()


def is_action_only(reply: str) -> bool:
    """判定大模型返回的是否仅为动作指令而无实质对话台词"""
    cleaned = strip_action_tags(reply)
    valid_chars = "".join(
        c for c in cleaned
        if c.isalnum() or '\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff'
    )
    return len(valid_chars) == 0


def mood_sound(reply: str) -> str:
    """针对纯动作状态的通用情绪发音"""
    for k, v in [
        ("哭", "呜……"), ("笑", "呵。"), ("生气", "哼。"), ("喵", "……"),
        ("思考", "唔……"), ("害羞", "……啊。"), ("惊讶", "……哇。"), ("再见", "嗯。"),
        ("认真", "嗯。"), ("沉默", "……"), ("歪", "嗯？"), ("看", "嗯？")
    ]:
        if k in (reply or ""):
            return v
    return "……"


def _match_exact_or_case(target: str, candidates: list):
    """不区分大小写精确匹配"""
    if not target or not candidates:
        return target
    for c in candidates:
        if c.lower() == target.lower():
            return c
    return target


def _find_best_match(keywords: list, candidates: list):
    """在候选列表中寻找包含指定关键词的项"""
    if not candidates:
        return None
    for kw in keywords:
        for c in candidates:
            if kw.lower() in c.lower():
                return c
    return None
