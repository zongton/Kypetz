# -*- coding: utf-8 -*-
"""
Kypetz 控制中心 (Kypetz Dashboard) 模块
提供大模型 API 切换、提示词实时调试、模型动态扫描与换装、日志流监控及 GitHub 热更新检查。
"""

import os
import sys
import re
import json
import shutil
import zipfile
import tempfile
import threading
import urllib.request
import urllib.parse
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QComboBox, QFileDialog, QMessageBox,
    QScrollArea, QFrame, QStackedWidget, QWidget, QApplication, QPlainTextEdit, QTextBrowser
)

from core.config import (
    APP_VERSION, APP_NAME, DEFAULT_GITHUB_REPO, BASE_DIR,
    _log_emitter, get_dynamic_prompt, DEFAULT_PROMPT
)
from core.llm import fetch_models
from ui.widgets import SVGS, make_svg_icon, make_svg_label, SegmentedButton


def scan_available_models() -> list:
    """
    动态递归扫描 Live2D 目录，自动发现所有可用的 Live2D 模型。
    只要文件夹内包含 index.json、model.json 或 *.model3.json，即识别为一个有效模型。
    """
    models = []
    base_model_dir = os.path.join(BASE_DIR, "Live2D", "live2d-model")
    if not os.path.exists(base_model_dir):
        return models

    for root, dirs, files in os.walk(base_model_dir):
        cfg_file = None
        for f in ["index.json", "model.json"]:
            if f in files:
                cfg_file = f
                break
        if not cfg_file:
            for f in files:
                if f.endswith(".model3.json"):
                    cfg_file = f
                    break

        if cfg_file:
            rel_dir = os.path.relpath(root, base_model_dir).replace("\\", "/")
            folder_name = os.path.basename(root)
            m_count = 0
            model_display_name = folder_name
            try:
                with open(os.path.join(root, cfg_file), "r", encoding="utf-8", errors="ignore") as jf:
                    meta = json.load(jf)
                    motions_obj = meta.get("motions")
                    if isinstance(motions_obj, dict):
                        m_count = len(motions_obj)
                    if meta.get("name"):
                        model_display_name = meta.get("name") + " (" + folder_name + ")"
            except Exception:
                pass

            tag = " [" + str(m_count) + "动作]" if m_count else ""
            # 统一使用标准的 live2d-model/ 规范相对路径，杜绝路径拼接歧义
            model_key = f"live2d-model/{rel_dir}"
            models.append({
                "key": model_key,
                "name": model_display_name + tag,
                "path": root
            })
    return models

# ---------------- 内置轻量 Markdown 渲染引擎 ----------------
def render_markdown_content(raw_text: str) -> str:
    """
    依照 GitHub GFM (GitHub Flavored Markdown) 标准规格渲染 Markdown 文档。
    采用标准 GitHub Dark Primer 规范样式：包含标准表格、行内代码徽章、代码块等宽字体与标题边框。
    特殊字符高保真保护：采用 Token 占位算法，确保 #, ", * 等在代码块、表格和正文中绝不发生语法污染。
    """
    if not raw_text:
        return "<p style='color:#8b949e; padding:12px;'>暂无文档内容。</p>"

    # 0. 跨平台换行符严格归一化 (统一将 Windows \r\n 转换为标准 \n，根除代码块匹配失效导致的架构树排版错乱)
    normalized_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    # 1. 代码块安全提取与保护 (防止代码内的 #, *, ", ' 被语法解析篡改)
    code_blocks = []
    def save_fenced_code(m):
        lang = m.group(1) or ""
        code_content = m.group(2)
        escaped_code = (code_content
                        .replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                        .replace('"', "&quot;")
                        .replace("'", "&#39;"))
        token = f"@@KYPETZ_FENCED_CODE_{len(code_blocks)}@@"
        # 采用 Qt 原生强制保留换行与对齐的 <pre> 块级标签，彻底解决 QTextBrowser 换行折叠导致架构树错乱的 Bug
        html = (
            f"<pre style='background-color:#161b22; border:1px solid #30363d; border-radius:6px; "
            f"padding:12px 14px; margin:10px 0; font-family:Consolas, Monaco, monospace; "
            f"font-size:12px; color:#e6edf3; line-height:1.45;'>"
            f"{escaped_code}</pre>"
        )
        code_blocks.append(html)
        return f"\n\n{token}\n\n"

    # 提取 ```代码块```
    text_content = re.sub(r"```([a-zA-Z0-9_\+\-]*)\n([\s\S]*?)```", save_fenced_code, normalized_text)

    # 2. 行内代码安全提取与保护
    inline_codes = []
    def save_inline_code(m):
        code_content = m.group(1)
        escaped_code = (code_content
                        .replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                        .replace('"', "&quot;")
                        .replace("'", "&#39;"))
        token = f"@@KYPETZ_INLINE_CODE_{len(inline_codes)}@@"
        html = (
            f"<code style='background-color:rgba(110,118,129,0.35); color:#f0f6fc; "
            f"padding:2px 6px; border-radius:4px; font-family:Consolas, monospace; font-size:12px;'>"
            f"{escaped_code}</code>"
        )
        inline_codes.append(html)
        return token

    # 提取 `code`
    text_content = re.sub(r"`([^`\n]+)`", save_inline_code, text_content)

    # 3. 逐行解析 Markdown 块级结构
    lines = text_content.splitlines()
    out_lines = []
    in_table = False
    in_list = False
    table_row_count = 0

    for line in lines:
        line_s = line.strip()

        # 空行
        if not line_s:
            if in_table:
                out_lines.append("</tbody></table>")
                in_table = False
                table_row_count = 0
            if in_list:
                out_lines.append("</ul>")
                in_list = False
            continue

        # 检查是否为被保护的代码块 token
        if line_s.startswith("@@KYPETZ_FENCED_CODE_") and line_s.endswith("@@"):
            if in_table:
                out_lines.append("</tbody></table>")
                in_table = False
            if in_list:
                out_lines.append("</ul>")
                in_list = False
            out_lines.append(line_s)
            continue

        # 表格处理 (GFM Table)
        if line_s.startswith("|") and line_s.endswith("|"):
            parts = [c.strip() for c in line_s.split("|")[1:-1]]
            # 过滤分隔行 | --- | --- |
            if all(set(c).issubset({'-', ':', ' ', '|'}) for c in parts if c):
                continue

            if not in_table:
                in_table = True
                table_row_count = 0
                out_lines.append(
                    "<table border='1' cellpadding='8' cellspacing='0' style='border-collapse:collapse; "
                    "border:1px solid #30363d; background-color:#0d1117; width:100%; margin:12px 0;'>"
                    "<thead><tr>" +
                    "".join(f"<th style='background-color:#161b22; color:#f0f6fc; font-weight:600; text-align:left; border:1px solid #30363d; padding:8px 12px; font-size:13px;'>{c}</th>" for c in parts) +
                    "</tr></thead><tbody>"
                )
            else:
                table_row_count += 1
                bg_color = "rgba(22, 27, 34, 0.75)" if table_row_count % 2 == 0 else "#0d1117"
                out_lines.append(
                    f"<tr style='background-color:{bg_color};'>" +
                    "".join(f"<td style='border:1px solid #30363d; padding:8px 12px; color:#c9d1d9; font-size:12.5px;'>{c}</td>" for c in parts) +
                    "</tr>"
                )
            continue
        elif in_table:
            out_lines.append("</tbody></table>")
            in_table = False
            table_row_count = 0

        # 分割线
        if line_s in ["---", "***", "___"]:
            if in_list:
                out_lines.append("</ul>")
                in_list = False
            out_lines.append("<hr style='border:none; height:1px; background-color:#30363d; margin:18px 0;' />")
            continue

        # 标题 (带标准 GitHub 下边框)
        if line_s.startswith("# "):
            if in_list:
                out_lines.append("</ul>")
                in_list = False
            out_lines.append(f"<h1 style='color:#f0f6fc; font-size:20px; font-weight:600; border-bottom:1px solid #30363d; padding-bottom:6px; margin-top:22px; margin-bottom:12px;'>{line_s[2:]}</h1>")
            continue
        if line_s.startswith("## "):
            if in_list:
                out_lines.append("</ul>")
                in_list = False
            out_lines.append(f"<h2 style='color:#f0f6fc; font-size:16.5px; font-weight:600; border-bottom:1px solid #30363d; padding-bottom:5px; margin-top:18px; margin-bottom:10px;'>{line_s[3:]}</h2>")
            continue
        if line_s.startswith("### "):
            if in_list:
                out_lines.append("</ul>")
                in_list = False
            out_lines.append(f"<h3 style='color:#f0f6fc; font-size:14.5px; font-weight:600; margin-top:14px; margin-bottom:8px;'>{line_s[4:]}</h3>")
            continue
        if line_s.startswith("#### "):
            if in_list:
                out_lines.append("</ul>")
                in_list = False
            out_lines.append(f"<h4 style='color:#f0f6fc; font-size:13px; font-weight:600; margin-top:12px; margin-bottom:6px;'>{line_s[5:]}</h4>")
            continue

        # 引用块
        if line_s.startswith("> "):
            if in_list:
                out_lines.append("</ul>")
                in_list = False
            out_lines.append(f"<div style='border-left:3px solid #388bfd; background-color:rgba(56,139,253,0.1); padding:8px 12px; margin:10px 0; color:#8b949e; border-radius:0 4px 4px 0;'>{line_s[2:]}</div>")
            continue

        # 列表项
        if line_s.startswith("- ") or line_s.startswith("* "):
            if not in_list:
                out_lines.append("<ul style='margin:8px 0; padding-left:22px; color:#c9d1d9;'>")
                in_list = True
            out_lines.append(f"<li style='margin:3px 0; font-size:13px;'>{line_s[2:]}</li>")
            continue
        elif in_list:
            out_lines.append("</ul>")
            in_list = False

        # 普通段落
        out_lines.append(f"<p style='margin:8px 0; color:#c9d1d9; font-size:13px; line-height:1.6;'>{line_s}</p>")

    if in_table:
        out_lines.append("</tbody></table>")
    if in_list:
        out_lines.append("</ul>")

    rendered_html = "\n".join(out_lines)

    # 4. 行内标记安全替换 (此时代码块与行内代码都已被 token 保护，绝不会被误伤)
    rendered_html = re.sub(r"\*\*([^\*\n]+)\*\*", r"<strong style='color:#f0f6fc; font-weight:600;'>\1</strong>", rendered_html)
    rendered_html = re.sub(r"(?<!\*)\*([^\*\n]+)\*(?!\*)", r"<em>\1</em>", rendered_html)
    rendered_html = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<a href='\2' style='color:#58a6ff; text-decoration:none;'>\1</a>", rendered_html)

    # 5. 还原被保护的代码块与行内代码
    for idx, token_html in enumerate(code_blocks):
        rendered_html = rendered_html.replace(f"@@KYPETZ_FENCED_CODE_{idx}@@", token_html)

    for idx, token_html in enumerate(inline_codes):
        rendered_html = rendered_html.replace(f"@@KYPETZ_INLINE_CODE_{idx}@@", token_html)

    # 包装全局容器与滚动样式
    container = (
        "<div style='font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; "
        "background-color:#0d1117; color:#c9d1d9; padding:12px 18px; line-height:1.6;'>"
        f"{rendered_html}</div>"
    )
    return container

# ---------------- KYPETZ CORE · 独立悬浮控制中枢 ----------------
class KypetzDashboard(QDialog):
    def __init__(self, cfg=None, save_cb=None, fetch_cb=None, change_skin_cb=None, parent=None, **kwargs):
        parent = parent or kwargs.get("parent")
        super().__init__(parent)
        self.cfg = cfg if isinstance(cfg, dict) else (kwargs.get("cfg") or {})
        self.save_cb = save_cb or kwargs.get("save_cb") or kwargs.get("save_callback")
        self.fetch_cb = fetch_cb or kwargs.get("fetch_cb") or kwargs.get("fetch_callback")
        self.change_skin_cb = change_skin_cb or kwargs.get("change_skin_cb") or kwargs.get("skin_callback")
        # 实时连接全局标准输出日志流
        _log_emitter.log_signal.connect(self.append_log)
        self.setWindowIcon(make_svg_icon(SVGS["cat"], 32))
        self.setWindowTitle("Kypetz Core · 控制中枢")
        self.resize(780, 640)
        self.setMinimumSize(720, 560)
        self.setStyleSheet("""
            QDialog {
                background: #141418;
                color: #F5F5F7;
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Microsoft YaHei UI", sans-serif;
            }
            QLabel {
                color: rgba(255, 255, 255, 0.72);
                font-size: 13px;
                line-height: 1.4;
            }
            QLineEdit, QComboBox {
                background: rgba(0, 0, 0, 0.35);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
                color: #ffffff;
                padding: 8px 14px;
                font-size: 13.5px;
                min-height: 22px;
            }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
                border: 1px solid #0A84FF;
            }
            QTextEdit {
                background: rgba(0, 0, 0, 0.38);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                color: rgba(255, 255, 255, 0.95);
                padding: 12px;
                font-size: 13px;
                line-height: 1.6;
            }
            QPlainTextEdit {
                background: #09090C;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                color: #D1D1D6;
                padding: 12px;
                font-family: "SF Mono", Menlo, Consolas, monospace;
                font-size: 12px;
                line-height: 1.65;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 4px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.28);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QPushButton.action-btn {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 10px;
                color: #ffffff;
                font-size: 13px;
                font-weight: 500;
                padding: 8px 20px;
                min-height: 22px;
            }
            QPushButton.action-btn:hover {
                background: rgba(255, 255, 255, 0.16);
            }
            QPushButton.primary-btn {
                background: #0A84FF;
                border: none;
                border-radius: 10px;
                color: #ffffff;
                font-size: 13.5px;
                font-weight: 600;
                padding: 8px 24px;
                min-height: 22px;
            }
            QPushButton.primary-btn:hover {
                background: #0077ED;
            }
            QPushButton.primary-btn:pressed {
                background: #005BB5;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 20)
        main_layout.setSpacing(14)

        # 1. 顶部品牌条 + 悬浮胶囊切页
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 0, 4, 0)

        brand_layout = QHBoxLayout()
        brand_layout.setSpacing(8)
        brand_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        brand_logo = make_svg_label(SVGS["cat"], 22)
        brand_text = QLabel("KYPETZ CORE")
        brand_text.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        brand_text.setStyleSheet("color: #ffffff; font-weight: 700; font-size: 14px; letter-spacing: 0.5px;")
        brand_sub = QLabel("· 控制中枢")
        brand_sub.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        brand_sub.setStyleSheet("color: rgba(255, 255, 255, 0.4); font-size: 11.5px;")
        brand_layout.addWidget(brand_logo)
        brand_layout.addWidget(brand_text)
        brand_layout.addWidget(brand_sub)
        top_bar.addLayout(brand_layout)

        top_bar.addStretch(1)

        self.seg_nav = SegmentedButton(["核心配置", "灵魂人设", "运行日志", "文档与更新"], self)
        self.seg_nav.changed.connect(self.on_tab_changed)
        top_bar.addWidget(self.seg_nav)

        main_layout.addLayout(top_bar)

        # 2. 页面容器
        self.stack = QStackedWidget(self)

        # Tab 0: 核心配置 (分块卡片)
        page0 = QWidget()
        p0_layout = QVBoxLayout(page0)
        p0_layout.setContentsMargins(0, 4, 0, 0)
        p0_layout.setSpacing(10)

        scroll0 = QScrollArea(page0)
        scroll0.setWidgetResizable(True)
        scroll0.setFrameShape(QFrame.NoFrame)
        scroll0.setStyleSheet("background: transparent; border: none;")

        scroll_content = QWidget()
        sc_layout = QVBoxLayout(scroll_content)
        sc_layout.setContentsMargins(0, 0, 4, 0)
        sc_layout.setSpacing(10)

        # --- 卡片 1: 称呼设定 ---
        card_id = QFrame()
        card_id.setStyleSheet("background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 12px; padding: 12px;")
        c_id_l = QVBoxLayout(card_id)
        c_id_l.setSpacing(6)

        lbl_id_box = QHBoxLayout()
        lbl_id_box.setContentsMargins(0, 0, 0, 0)
        lbl_id_box.setSpacing(8)
        lbl_id_box.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_id_box.addWidget(make_svg_label(SVGS["user"], 22, stroke_color="#64D2FF"))
        lbl_id = QLabel("称呼与身份设定")
        lbl_id.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_id.setStyleSheet("color: #ffffff; font-weight: 600; font-size: 13.5px;")
        lbl_id_box.addWidget(lbl_id)
        lbl_id_box.addStretch(1)
        c_id_l.addLayout(lbl_id_box)

        id_row = QHBoxLayout()
        v_pet = QVBoxLayout()
        v_pet.addWidget(QLabel("桌宠角色名字 (如: 小助手 / 爱丽丝 / 乐奈)"))
        self.edit_pet_name = QLineEdit(self.cfg.get("pet_name", "桌宠"))
        v_pet.addWidget(self.edit_pet_name)
        id_row.addLayout(v_pet, 1)

        v_user = QVBoxLayout()
        v_user.addWidget(QLabel("对你的称呼 (如: 主人 / 老师 / 朋友)"))
        self.edit_user_call = QLineEdit(self.cfg.get("user_call", "主人"))
        v_user.addWidget(self.edit_user_call)
        id_row.addLayout(v_user, 1)
        c_id_l.addLayout(id_row)
        sc_layout.addWidget(card_id)

        # --- 卡片 2: AI 大语言模型 API ---
        card_llm = QFrame()
        card_llm.setStyleSheet("background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 12px; padding: 12px;")
        c_llm_l = QVBoxLayout(card_llm)
        c_llm_l.setSpacing(8)

        lbl_llm_box = QHBoxLayout()
        lbl_llm_box.setContentsMargins(0, 0, 0, 0)
        lbl_llm_box.setSpacing(8)
        lbl_llm_box.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_llm_box.addWidget(make_svg_label(SVGS["cpu"], 22, stroke_color="#BF5AF2"))
        lbl_llm = QLabel("AI 对话大模型 (LLM API)")
        lbl_llm.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_llm.setStyleSheet("color: #ffffff; font-weight: 600; font-size: 13.5px;")
        lbl_llm_box.addWidget(lbl_llm)
        lbl_llm_box.addStretch(1)
        c_llm_l.addLayout(lbl_llm_box)

        c_llm_l.addWidget(QLabel("API 接口地址 (OpenAI 规范 / DeepSeek / Ollama)"))
        self.edit_base = QLineEdit(self.cfg.get("llm_base", ""))
        self.edit_base.setPlaceholderText("https://api.deepseek.com 或 http://127.0.0.1:11434/v1")
        c_llm_l.addWidget(self.edit_base)

        c_llm_l.addWidget(QLabel("API Key (授权令牌)"))
        self.edit_key = QLineEdit(self.cfg.get("llm_key", ""))
        self.edit_key.setEchoMode(QLineEdit.EchoMode.Password)
        c_llm_l.addWidget(self.edit_key)

        model_row = QHBoxLayout()
        model_v = QVBoxLayout()
        model_v.addWidget(QLabel("对话大模型"))
        self.combo_model = QComboBox()
        self.combo_model.setEditable(True)
        for m in self.cfg.get("llm_models", []):
            self.combo_model.addItem(m)
        if self.cfg.get("llm_model"):
            self.combo_model.setEditText(self.cfg["llm_model"])
        model_v.addWidget(self.combo_model)
        model_row.addLayout(model_v, 1)

        btn_fetch = QPushButton("拉取模型", self)
        btn_fetch.setProperty("class", "action-btn")
        btn_fetch.setFixedHeight(38)
        btn_fetch.setIcon(make_svg_icon(SVGS["search"], 16))
        btn_fetch.setIconSize(QSize(16, 16))
        btn_fetch.clicked.connect(self.do_fetch_models)
        model_row.addWidget(btn_fetch, 0, Qt.AlignmentFlag.AlignBottom)
        c_llm_l.addLayout(model_row)
        sc_layout.addWidget(card_llm)

        # --- 卡片 3: 语音合成服务 TTS ---
        card_tts = QFrame()
        card_tts.setStyleSheet("background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 12px; padding: 12px;")
        c_tts_l = QVBoxLayout(card_tts)
        c_tts_l.setSpacing(8)

        lbl_tts_box = QHBoxLayout()
        lbl_tts_box.setContentsMargins(0, 0, 0, 0)
        lbl_tts_box.setSpacing(8)
        lbl_tts_box.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_tts_box.addWidget(make_svg_label(SVGS["sound"], 22, stroke_color="#FFD60A"))
        lbl_tts = QLabel("语音合成服务 (TTS Voice)")
        lbl_tts.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_tts.setStyleSheet("color: #ffffff; font-weight: 600; font-size: 13.5px;")
        lbl_tts_box.addWidget(lbl_tts)
        lbl_tts_box.addStretch(1)
        c_tts_l.addLayout(lbl_tts_box)

        c_tts_l.addWidget(QLabel("GPT-SoVITS 本地服务端口 (留空自动走微软 Edge-TTS)"))
        self.edit_tts = QLineEdit(self.cfg.get("tts_url", ""))
        self.edit_tts.setPlaceholderText("例如: http://127.0.0.1:9880 (留空则使用微软 Edge-TTS)")
        c_tts_l.addWidget(self.edit_tts)

        # 语音发音语言切换 (中文 / 日语)
        lang_row = QHBoxLayout()
        lang_row.setContentsMargins(0, 4, 0, 0)
        lbl_vlang = QLabel("语音发音模式 (SoVITS 联动):")
        lbl_vlang.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-size: 12px;")
        lang_row.addWidget(lbl_vlang)
        lang_row.addStretch(1)

        self.combo_voice_lang = QComboBox()
        self.combo_voice_lang.addItem("中文语音 (中文字幕 + 中文发音)", "zh")
        self.combo_voice_lang.addItem("日语语音 (中文字幕 + 自动翻译日语发音)", "ja")
        cur_vlang = self.cfg.get("voice_lang", "zh")
        idx_v = self.combo_voice_lang.findData(cur_vlang)
        if idx_v >= 0:
            self.combo_voice_lang.setCurrentIndex(idx_v)
        lang_row.addWidget(self.combo_voice_lang)
        c_tts_l.addLayout(lang_row)

        sc_layout.addWidget(card_tts)

        # --- 卡片 4: Live2D 形象换装 ---
        card_skin = QFrame()
        card_skin.setStyleSheet("background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 12px; padding: 12px;")
        c_skin_l = QVBoxLayout(card_skin)
        c_skin_l.setSpacing(8)

        lbl_skin_box = QHBoxLayout()
        lbl_skin_box.setContentsMargins(0, 0, 0, 0)
        lbl_skin_box.setSpacing(8)
        lbl_skin_box.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_skin_box.addWidget(make_svg_label(SVGS["skin"], 22, stroke_color="#FF375F"))
        lbl_skin = QLabel("Live2D 角色形象 / 皮肤外观")
        lbl_skin.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl_skin.setStyleSheet("color: #ffffff; font-weight: 600; font-size: 13.5px;")
        lbl_skin_box.addWidget(lbl_skin)
        lbl_skin_box.addStretch(1)
        c_skin_l.addLayout(lbl_skin_box)

        skin_row = QHBoxLayout()
        self.combo_skin = QComboBox()
        cur_skin = self.cfg.get("live2d_model", "")
        discovered_models = scan_available_models()
        for m in discovered_models:
            self.combo_skin.addItem(m["name"], m["key"])
        # 若当前配置的模型不在扫描结果中（如外部自定义路径），自动追加
        if cur_skin and all(self.combo_skin.itemData(i) != cur_skin for i in range(self.combo_skin.count())):
            self.combo_skin.addItem(f"自定义路径 ({cur_skin})", cur_skin)
        for idx in range(self.combo_skin.count()):
            if self.combo_skin.itemData(idx) == cur_skin:
                self.combo_skin.setCurrentIndex(idx)
                break
        skin_row.addWidget(self.combo_skin, 1)
        c_skin_l.addLayout(skin_row)

        skin_btn_row = QHBoxLayout()
        btn_apply_skin = QPushButton("立即切换", self)
        btn_apply_skin.setProperty("class", "action-btn")
        btn_apply_skin.setFixedHeight(38)
        btn_apply_skin.clicked.connect(self.do_change_skin)

        btn_import_skin = QPushButton("导入外部模型文件夹...", self)
        btn_import_skin.setProperty("class", "action-btn")
        btn_import_skin.setFixedHeight(38)
        btn_import_skin.setIcon(make_svg_icon(SVGS["folder"], 16))
        btn_import_skin.setIconSize(QSize(16, 16))
        btn_import_skin.clicked.connect(self.do_import_custom_model)

        skin_btn_row.addWidget(btn_apply_skin)
        skin_btn_row.addWidget(btn_import_skin)
        c_skin_l.addLayout(skin_btn_row)
        sc_layout.addWidget(card_skin)

        scroll0.setWidget(scroll_content)
        p0_layout.addWidget(scroll0, 1)

        # 底部操作栏
        p0_actions = QHBoxLayout()
        btn_exit_app = QPushButton("退出桌宠", self)
        btn_exit_app.setFixedHeight(40)
        btn_exit_app.setIcon(make_svg_icon(SVGS["power"], 16, stroke_color="#FF453A"))
        btn_exit_app.setIconSize(QSize(16, 16))
        btn_exit_app.setStyleSheet("""
            QPushButton {
                background: rgba(255, 69, 58, 0.14);
                border: 1px solid rgba(255, 69, 58, 0.28);
                border-radius: 10px;
                color: #FF453A;
                font-size: 13px;
                font-weight: 600;
                padding: 8px 18px;
            }
            QPushButton:hover {
                background: rgba(255, 69, 58, 0.28);
                color: #ffffff;
            }
        """)
        btn_exit_app.clicked.connect(QApplication.instance().quit)
        p0_actions.addWidget(btn_exit_app)
        p0_actions.addStretch(1)

        btn_save0 = QPushButton("保存全部配置", self)
        btn_save0.setProperty("class", "primary-btn")
        btn_save0.setFixedHeight(40)
        btn_save0.clicked.connect(self.save_all)
        p0_actions.addWidget(btn_save0)
        p0_layout.addLayout(p0_actions)

        self.stack.addWidget(page0)

        # Tab 1: 灵魂人设
        page1 = QWidget()
        p1_layout = QVBoxLayout(page1)
        p1_layout.setContentsMargins(0, 6, 0, 0)
        p1_layout.setSpacing(12)

        p1_layout.addWidget(QLabel("系统人设 Prompt (实时指导 AI 的性格与 Live2D 动作编排)"))
        self.prompt_edit = QTextEdit(self)
        self.prompt_edit.setText(self.cfg.get("system_prompt", DEFAULT_PROMPT))
        p1_layout.addWidget(self.prompt_edit, 1)

        p1_actions = QHBoxLayout()
        btn_reset_prompt = QPushButton("恢复官方模版", self)
        btn_reset_prompt.setProperty("class", "action-btn")
        btn_reset_prompt.setFixedHeight(38)
        btn_reset_prompt.clicked.connect(lambda: self.prompt_edit.setText(DEFAULT_PROMPT))
        p1_actions.addWidget(btn_reset_prompt)
        p1_actions.addStretch(1)

        btn_save1 = QPushButton("更新人设并保存", self)
        btn_save1.setProperty("class", "primary-btn")
        btn_save1.setFixedHeight(40)
        btn_save1.clicked.connect(self.save_all)
        p1_actions.addWidget(btn_save1)
        p1_layout.addLayout(p1_actions)

        self.stack.addWidget(page1)

        # Tab 2: 运行日志流
        page2 = QWidget()
        p2_layout = QVBoxLayout(page2)
        p2_layout.setContentsMargins(0, 6, 0, 0)
        p2_layout.setSpacing(12)

        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("等待系统运行日志...")
        p2_layout.addWidget(self.log_view, 1)

        p2_actions = QHBoxLayout()
        p2_actions.addStretch(1)
        btn_clear_log = QPushButton("清空日志", self)
        btn_clear_log.setProperty("class", "action-btn")
        btn_clear_log.setFixedHeight(38)
        btn_clear_log.clicked.connect(self.log_view.clear)
        p2_actions.addWidget(btn_clear_log)
        p2_layout.addLayout(p2_actions)

        self.stack.addWidget(page2)

        # Tab 3: 文档浏览与版本更新 (Markdown 本地阅读器 + GitHub Release 更新)
        page3 = QWidget()
        p3_layout = QVBoxLayout(page3)
        p3_layout.setContentsMargins(0, 4, 0, 0)
        p3_layout.setSpacing(10)

        # 1. 顶部版本卡片与操作控制栏
        card_ver = QFrame()
        card_ver.setStyleSheet("background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 12px; padding: 10px 14px;")
        cv_l = QHBoxLayout(card_ver)
        cv_l.setContentsMargins(0, 0, 0, 0)
        cv_l.setSpacing(10)
        cv_l.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        ver_info_l = QHBoxLayout()
        ver_info_l.setContentsMargins(0, 0, 0, 0)
        ver_info_l.setSpacing(8)
        ver_info_l.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        cat_logo = make_svg_label(SVGS["cat"], 22)
        ver_info_l.addWidget(cat_logo)

        v_lbl = QLabel(f"Kypetz {APP_VERSION}")
        v_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        v_lbl.setStyleSheet("color: #ffffff; font-size: 15px; font-weight: 700; letter-spacing: -0.2px;")
        ver_info_l.addWidget(v_lbl)

        ver_badge = QLabel("Official")
        ver_badge.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ver_badge.setStyleSheet("color: #0A84FF; background: rgba(10, 132, 255, 0.14); padding: 3px 8px; border-radius: 6px; font-weight: 600; font-size: 11px;")
        ver_info_l.addWidget(ver_badge)
        cv_l.addLayout(ver_info_l)

        cv_l.addStretch(1)

        # Markdown 浏览器操作按钮
        self.btn_open_md = QPushButton("打开本地 Markdown...", self)
        self.btn_open_md.setProperty("class", "action-btn")
        self.btn_open_md.setFixedHeight(38)
        self.btn_open_md.setIcon(make_svg_icon(SVGS["folder"], 15))
        self.btn_open_md.setIconSize(QSize(15, 15))
        self.btn_open_md.clicked.connect(self.do_open_custom_markdown)
        cv_l.addWidget(self.btn_open_md)

        self.btn_reset_md = QPushButton("项目说明", self)
        self.btn_reset_md.setProperty("class", "action-btn")
        self.btn_reset_md.setFixedHeight(38)
        self.btn_reset_md.setIcon(make_svg_icon(SVGS["refresh"], 14))
        self.btn_reset_md.setIconSize(QSize(14, 14))
        self.btn_reset_md.clicked.connect(self.do_load_default_readme)
        cv_l.addWidget(self.btn_reset_md)

        self.btn_check_update = QPushButton("检查更新", self)
        self.btn_check_update.setProperty("class", "primary-btn")
        self.btn_check_update.setFixedHeight(38)
        self.btn_check_update.setIcon(make_svg_icon(SVGS["search"], 14))
        self.btn_check_update.setIconSize(QSize(14, 14))
        self.btn_check_update.clicked.connect(self.do_check_update)
        cv_l.addWidget(self.btn_check_update)

        p3_layout.addWidget(card_ver)

        # 2. 更新动态提示条 (发现新版本时展开)
        self.card_update_box = QFrame()
        self.card_update_box.setStyleSheet("background: rgba(10, 132, 255, 0.08); border: 1px solid rgba(10, 132, 255, 0.25); border-radius: 12px; padding: 12px;")
        cub_l = QVBoxLayout(self.card_update_box)
        cub_l.setSpacing(8)

        self.lbl_update_status = QLabel("点击【检查更新】可查询 GitHub 最新发布版本...")
        self.lbl_update_status.setStyleSheet("color: rgba(255, 255, 255, 0.85); font-size: 13px; font-weight: 500;")
        self.lbl_update_status.setWordWrap(True)
        cub_l.addWidget(self.lbl_update_status)

        self.update_notes = QTextEdit(self)
        self.update_notes.setReadOnly(True)
        self.update_notes.setFixedHeight(110)
        self.update_notes.setPlaceholderText("Release 更新日志说明...")
        self.update_notes.hide()
        cub_l.addWidget(self.update_notes)

        self.btn_do_upgrade = QPushButton("一键自动下载并热升级覆盖", self)
        self.btn_do_upgrade.setProperty("class", "primary-btn")
        self.btn_do_upgrade.setFixedHeight(40)
        self.btn_do_upgrade.setIcon(make_svg_icon(SVGS["rocket"], 15))
        self.btn_do_upgrade.setIconSize(QSize(15, 15))
        self.btn_do_upgrade.hide()
        self.btn_do_upgrade.clicked.connect(self.do_auto_upgrade)
        cub_l.addWidget(self.btn_do_upgrade)

        p3_layout.addWidget(self.card_update_box)

        # 3. 文档路径状态指示
        self.doc_status_lbl = QLabel("当前查看文档: 项目说明 (README.md)")
        self.doc_status_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.45); font-size: 11.5px; padding-left: 2px;")
        p3_layout.addWidget(self.doc_status_lbl)

        # 4. 官方 Markdown 渲染展示区
        self.doc_browser = QTextBrowser(self)
        self.doc_browser.setOpenExternalLinks(True)
        self.doc_browser.setStyleSheet("""
            QTextBrowser {
                background: rgba(0, 0, 0, 0.38);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                color: #D1D1D6;
                padding: 16px;
                font-size: 13px;
                line-height: 1.68;
            }
        """)
        self.do_load_default_readme()
        p3_layout.addWidget(self.doc_browser, 1)

        self.stack.addWidget(page3)

        main_layout.addWidget(self.stack, 1)

        self.latest_zip_url = None
        self.latest_ver_tag = None

    def do_load_default_readme(self):
        readme_file = os.path.join(BASE_DIR, "README.md")
        if os.path.exists(readme_file):
            try:
                with open(readme_file, "r", encoding="utf-8") as f:
                    content = f.read()
                self.doc_browser.setHtml(render_markdown_content(content))
                self.doc_status_lbl.setText("当前查看文档: 项目说明 (README.md)")
            except Exception as e:
                self.doc_browser.setPlainText(f"加载 README.md 异常: {e}")
        else:
            self.doc_browser.setPlainText("未在项目目录下找到 README.md 文档。")

    def do_open_custom_markdown(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择本地 Markdown 文档", BASE_DIR, "Markdown 文档 (*.md *.markdown *.txt);;所有文件 (*.*)"
        )
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.doc_browser.setHtml(render_markdown_content(content))
            filename = os.path.basename(file_path)
            self.doc_status_lbl.setText(f"当前查看文档: {filename} ({file_path})")
            self.append_log(f"[DOC] 已成功载入本地 Markdown 文档: {filename} ✓")
        except Exception as e:
            QMessageBox.critical(self, "读取失败", f"打开 Markdown 文档出错:\n{e}")

    def on_tab_changed(self, idx):
        self.stack.setCurrentIndex(idx)

    def append_log(self, text):
        self.log_view.appendPlainText(text.strip())
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def do_fetch_models(self):
        if self.fetch_cb:
            try:
                ms = self.fetch_cb(self.edit_base.text().strip(), self.edit_key.text().strip())
                self.combo_model.clear()
                self.combo_model.addItems(ms)
                self.append_log(f"[INFO] 成功拉取到 {len(ms)} 个模型")
            except Exception as e:
                self.append_log(f"[ERROR] 获取模型失败: {e}")

    def do_change_skin(self):
        skin_key = self.combo_skin.currentData()
        if skin_key:
            self.cfg["live2d_model"] = skin_key
            if self.save_cb:
                self.save_cb(self.cfg)
            if self.change_skin_cb:
                self.change_skin_cb(skin_key)
            self.append_log(f"[MODEL] 角色形象已切换为: {self.combo_skin.currentText()} ✓")

    def do_import_custom_model(self):
        folder = QFileDialog.getExistingDirectory(self, "选择 Live2D 角色模型文件夹 (包含 index.json 或 model.json)")
        if not folder:
            return
        folder_name = os.path.basename(os.path.normpath(folder))
        # 扫描该目录下是否包含 json 文件
        jsons = [f for f in os.listdir(folder) if f.endswith(".json")]
        if not jsons:
            QMessageBox.warning(self, "未检测到模型描述文件", "所选文件夹内未检测到任何 .json 模型描述文件！")
            return

        target_dir = os.path.join(BASE_DIR, "Live2D", "live2d-model", folder_name)
        try:
            import shutil
            if os.path.abspath(folder) != os.path.abspath(target_dir):
                if os.path.exists(target_dir):
                    shutil.rmtree(target_dir)
                shutil.copytree(folder, target_dir)

            display_name = f"自定义 · {folder_name}"
            canonical_key = f"live2d-model/{folder_name}"
            found_idx = -1
            for i in range(self.combo_skin.count()):
                if self.combo_skin.itemData(i) == canonical_key:
                    found_idx = i
                    break
            if found_idx >= 0:
                self.combo_skin.setCurrentIndex(found_idx)
            else:
                self.combo_skin.addItem(display_name, canonical_key)
                self.combo_skin.setCurrentIndex(self.combo_skin.count() - 1)

            self.do_change_skin()
            QMessageBox.information(self, "导入成功", f"模型【{folder_name}】已成功导入并载入舞台！")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"导入模型出错: {e}")

    def do_check_update(self):
        repo = DEFAULT_GITHUB_REPO
        self.btn_check_update.setEnabled(False)
        self.lbl_update_status.setText("正在向 GitHub 查询最新 Release 版本...")
        self.update_notes.hide()
        self.btn_do_upgrade.hide()

        def _worker():
            try:
                url = f"https://api.github.com/repos/{repo}/releases/latest"
                req = urllib.request.Request(url, headers={"User-Agent": "Kypet-App"})
                with urllib.request.urlopen(req, timeout=12) as r:
                    data = json.loads(r.read().decode("utf-8"))

                tag = data.get("tag_name", "").strip()
                body = data.get("body", "暂无详细更新说明。")
                name = data.get("name", tag)

                # 寻找 zip 包下载地址 (优先 release assets 中的 zip，其次源码 zipball)
                zip_url = data.get("zipball_url")
                for asset in data.get("assets", []):
                    if asset.get("name", "").endswith(".zip"):
                        zip_url = asset.get("browser_download_url")
                        break

                # 比较版本号
                remote_clean = tag.lstrip("vV")
                local_clean = APP_VERSION.lstrip("vV")

                def _ui_done():
                    self.btn_check_update.setEnabled(True)
                    if remote_clean and remote_clean != local_clean:
                        self.latest_zip_url = zip_url
                        self.latest_ver_tag = tag
                        self.lbl_update_status.setText(f"🎉 发现新版本: {tag} ({name})！当前运行版本: {APP_VERSION}")
                        self.update_notes.setText(body)
                        self.update_notes.show()
                        if zip_url:
                            self.btn_do_upgrade.setText(f"🚀 一键自动下载并热升级至 {tag}")
                            self.btn_do_upgrade.show()
                        self.append_log(f"[UPDATE] 检查到新版本: {tag} ✓")
                    else:
                        self.lbl_update_status.setText(f"🎉 当前已是最新版本 ({APP_VERSION})，无需更新。")
                        self.append_log(f"[UPDATE] 当前已是最新版本 ({APP_VERSION}) ✓")

                QTimer.singleShot(0, _ui_done)

            except Exception as e:
                def _ui_err(err_msg):
                    self.btn_check_update.setEnabled(True)
                    if "404" in err_msg:
                        self.lbl_update_status.setText(f"当前已是最新发布版本 ({APP_VERSION}) ✓")
                    else:
                        self.lbl_update_status.setText(f"检查更新完成: 当前为最新版本或未检测到新 Release。")
                    self.append_log(f"[UPDATE] 检查更新状态: {err_msg}")
                QTimer.singleShot(0, lambda: _ui_err(str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def do_auto_upgrade(self):
        if not self.latest_zip_url:
            QMessageBox.warning(self, "提示", "未找到可供下载的新版本安装包。")
            return

        confirm = QMessageBox.question(
            self, "确认一键升级",
            f"即将自动下载并热升级至 {self.latest_ver_tag}！\n\n"
            "【特别安全保护】：升级过程中将严格保留你的本地配置文件 (config.json)，绝不会重置你的 API Key 与个人配置。\n\n"
            "是否立即开始自动升级？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.btn_do_upgrade.setEnabled(False)
        self.lbl_update_status.setText("正在极速下载更新压缩包，请稍候...")

        def _upgrade_worker():
            import zipfile
            temp_zip = os.path.join(tempfile.gettempdir(), f"kypet_update_{os.urandom(4).hex()}.zip")
            try:
                # 1. 下载新版本 zip 包
                req = urllib.request.Request(self.latest_zip_url, headers={"User-Agent": "Kypet-App"})
                with urllib.request.urlopen(req, timeout=120) as r, open(temp_zip, "wb") as f:
                    f.write(r.read())

                # 2. 解压覆盖到本地目录 (严格跳过 config.json 防止覆盖私钥)
                with zipfile.ZipFile(temp_zip, 'r') as zf:
                    namelist = zf.namelist()
                    prefix = ""
                    first_item = namelist[0] if namelist else ""
                    if "/" in first_item:
                        top_dir = first_item.split("/")[0] + "/"
                        if all(name.startswith(top_dir) for name in namelist if name):
                            prefix = top_dir

                    for member in zf.infolist():
                        rel_path = member.filename[len(prefix):] if prefix and member.filename.startswith(prefix) else member.filename
                        if not rel_path or rel_path.endswith("/"):
                            continue

                        # 核心防覆盖保护：绝不覆盖本地私钥配置文件！
                        if os.path.basename(rel_path).lower() in ["config.json"]:
                            continue

                        dest_file = os.path.join(BASE_DIR, rel_path)
                        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                        with zf.open(member) as src, open(dest_file, "wb") as dst:
                            dst.write(src.read())

                def _upgrade_success():
                    self.lbl_update_status.setText(f"🎉 升级完成！已成功更新至 {self.latest_ver_tag}。")
                    self.append_log(f"[UPDATE] 自动覆盖升级完成，版本: {self.latest_ver_tag} ✓")
                    QMessageBox.information(
                        self, "升级成功",
                        f"Kypet 已成功自动热升级至 {self.latest_ver_tag}！\n\n点击确定退出程序，重新启动即可享受最新功能。"
                    )
                    QApplication.instance().quit()

                QTimer.singleShot(0, _upgrade_success)

            except Exception as e:
                def _upgrade_fail(err):
                    self.btn_do_upgrade.setEnabled(True)
                    self.lbl_update_status.setText(f"升级失败: {err}")
                    self.append_log(f"[UPDATE] 升级失败: {err}")
                    QMessageBox.critical(self, "升级异常", f"自动更新出错:\n{err}")
                QTimer.singleShot(0, lambda: _upgrade_fail(str(e)))
            finally:
                if os.path.exists(temp_zip):
                    try: os.remove(temp_zip)
                    except Exception: pass

        threading.Thread(target=_upgrade_worker, daemon=True).start()

    def save_all(self):
        self.cfg["pet_name"] = self.edit_pet_name.text().strip() or "桌宠"
        self.cfg["user_call"] = self.edit_user_call.text().strip() or "主人"
        self.cfg["llm_base"] = self.edit_base.text().strip()
        self.cfg["llm_key"] = self.edit_key.text().strip()
        self.cfg["llm_model"] = self.combo_model.currentText().strip()
        self.cfg["llm_models"] = [self.combo_model.itemText(i) for i in range(self.combo_model.count()) if self.combo_model.itemText(i)]
        self.cfg["tts_url"] = self.edit_tts.text().strip()
        self.cfg["voice_lang"] = self.combo_voice_lang.currentData()
        self.cfg["system_prompt"] = self.prompt_edit.toPlainText().strip()
        self.cfg["live2d_model"] = self.combo_skin.currentData()
        if self.save_cb:
            self.save_cb(self.cfg)
        self.append_log("[CONFIG] 配置与人设已保存并实时生效 ✓")
        self.accept()

# ---------------- 主程序入口 ----------------
