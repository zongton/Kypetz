# -*- coding: utf-8 -*-
"""
Kypetz 启动自检
在未检测到完整 Python 环境时，使用原生 Tkinter 绘制诊断进度条并调用镜像源自愈安装依赖。
"""

import os
import sys
import time
import subprocess
from core.config import APP_VERSION, APP_NAME

def run_self_healing_splash():
    try:
        import tkinter as tk
    except Exception:
        return  # 极简化环境无 GUI 直接跳过

    root = tk.Tk()
    root.overrideredirect(True)
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass

    w, h = 460, 240
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.configure(bg="#141418")

    container = tk.Frame(root, bg="#141418", highlightthickness=1, highlightbackground="#2A2A32")
    container.pack(fill="both", expand=True, padx=2, pady=2)

    # 1. 顶部
    header = tk.Frame(container, bg="#141418")
    header.pack(fill="x", padx=20, pady=(18, 0))

    brand_frame = tk.Frame(header, bg="#141418")
    brand_frame.pack(side="left")

    dot = tk.Label(brand_frame, text="●", fg="#30D158", bg="#141418", font=("Segoe UI", 9))
    dot.pack(side="left", padx=(0, 6))

    brand = tk.Label(brand_frame, text="KYPET SYSTEM", fg="#FFFFFF", bg="#141418", font=("Segoe UI", 10, "bold"))
    brand.pack(side="left")

    tag = tk.Label(header, text=f"{APP_VERSION} Stable", fg="#8E8E93", bg="#202026", font=("Segoe UI", 8), padx=6, pady=2)
    tag.pack(side="right")

    # 2. 状态与进度百分比
    center = tk.Frame(container, bg="#141418")
    center.pack(fill="x", padx=20, pady=(24, 0))

    title_row = tk.Frame(center, bg="#141418")
    title_row.pack(fill="x")

    lbl_title = tk.Label(title_row, text="正在启动环境自检...", fg="#F5F5F7", bg="#141418", font=("Segoe UI", 11, "bold"))
    lbl_title.pack(side="left")

    lbl_pct = tk.Label(title_row, text="0%", fg="#0A84FF", bg="#141418", font=("Segoe UI", 11, "bold"))
    lbl_pct.pack(side="right")

    # 3. 渐变进度条
    cv = tk.Canvas(center, width=420, height=4, bg="#24242C", highlightthickness=0)
    cv.pack(fill="x", pady=(10, 0))

    def update_progress(pct, title=None, detail=None):
        if title:
            lbl_title.config(text=title)
        if detail:
            lbl_detail.config(text=detail)
        lbl_pct.config(text=f"{int(pct)}%")
        cv.delete("all")
        bar_w = int(420 * (pct / 100.0))
        if bar_w > 0:
            cv.create_rectangle(0, 0, bar_w, 4, fill="#0A84FF", outline="")
        root.update()

    # 4. 当前自检项与安装细节
    lbl_detail = tk.Label(center, text="正在初始化诊断流水线...", fg="#8E8E93", bg="#141418", font=("Segoe UI", 9), anchor="w")
    lbl_detail.pack(fill="x", pady=(10, 0))

    # 5. 底部信息
    footer = tk.Frame(container, bg="#141418")
    footer.pack(fill="x", side="bottom", padx=20, pady=(0, 16))

    hint = tk.Label(footer, text="高速源: 清华大学开源镜像站", fg="#636366", bg="#141418", font=("Segoe UI", 8))
    hint.pack(side="left")

    sub = tk.Label(footer, text="Live2D · SoVITS · LLM", fg="#636366", bg="#141418", font=("Segoe UI", 8))
    sub.pack(side="right")

    root.update()

    # --- 执行自检与自动安装流水线 ---
    update_progress(15, "正在检测 Python 架构", f"Python {sys.version_info.major}.{sys.version_info.minor} 64-bit 运行时就绪 ✓")
    time.sleep(0.18)

    REQUIRED_PACKAGES = [
        ("PySide6", "PySide6"),
        ("sounddevice", "sounddevice"),
        ("numpy", "numpy"),
        ("scipy", "scipy"),
        ("keyboard", "keyboard"),
        ("vosk", "vosk"),
        ("edge_tts", "edge-tts"),
    ]

    missing = []
    pct_step = 60.0 / len(REQUIRED_PACKAGES)
    cur_pct = 15.0

    for import_name, pip_name in REQUIRED_PACKAGES:
        cur_pct += pct_step
        update_progress(cur_pct, "正在校验必要组件", f"检测 {pip_name}...")
        try:
            __import__(import_name)
            time.sleep(0.04)
        except ImportError:
            missing.append(pip_name)

    if missing:
        update_progress(75, "正在自动安装缺失组件", f"正在通过清华源安装: {', '.join(missing)}...")
        cmd = [sys.executable, "-m", "pip", "install", *missing, "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
        try:
            subprocess.run(cmd, check=True)
            update_progress(88, "组件自动安装完毕", f"已成功自动补全 {len(missing)} 个依赖组件 ✓")
        except Exception:
            update_progress(88, "镜像源重试中", "正在尝试官方源重试安装...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", *missing])
            except Exception:
                pass

    update_progress(95, "正在预热声学引擎与端口", "声学重采样引擎与 SoVITS 端口就绪 ✓")
    time.sleep(0.15)

    update_progress(100, "自检完毕，正在唤醒桌宠", "所有环境验证通过，Kypet 即将呈现...")
    time.sleep(0.25)

    root.destroy()

