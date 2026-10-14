# -*- coding: utf-8 -*-
"""
Kypetz 一键自动化发布到 GitHub 工具 (增强网络容灾与代理支持版)
免装 Git 客户端，纯基于 GitHub 官方 REST API：
1. 自动智能检测系统代理或本地科学加速端口 (如 7890, 10809, 10808)
2. 自动校验 / 创建远程公开仓库 (zongton/Kypetz)
3. 自动创建 v1.0.0 正式 Release 版本与 Tag
4. 自动上传 dist/Kypetz-v1.0.0-Windows.zip 资产包
"""

import os
import sys
import json
import urllib.request
import urllib.error
import socket

REPO_OWNER = "zongton"
REPO_NAME = "Kypetz"
TAG_NAME = "v1.0.0"
RELEASE_NAME = "Kypetz v1.0.0 - Official Release"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ZIP_PATH = os.path.join(BASE_DIR, "dist", "Kypetz-v1.0.0-Windows.zip")

RELEASE_BODY = """### 🎉 Kypetz v1.0.0 正式发布！

Kypetz 是一个基于 Python (PySide6) 和 Live2D 的开源桌面 AI 伴侣软件。

#### ✨ 核心特性
- **Live2D 桌面伴侣**：支持透明无边框窗口、鼠标随意拖拽、滚轮无级缩放以及 1:1 像素复位。
- **大模型指令驱动与动作自适应**：支持大模型通过 `[action: 动作名, 表情名]` 直接操控桌面形象，自动自省模型元数据，换模型全自动适配。
- **双模智能语音输出 (TTS)**：支持本地 GPT-SoVITS 与微软 Edge-TTS 在线合成，支持**日语语音发音 + 中文字幕**同屏展示！
- **离线语音识别 (ASR)**：项目自带集成 Vosk 离线模型，按住 Ctrl 即可高灵敏拾音。
- **真·自主挂机思考搭话**：静置超过 1 分钟后，大模型自主调用 API 构思话题找主人聊天。
- **独立极客控制中心**：现代 Apple 磨砂风格，实时监控运行日志流，模型一键扫描换装。

#### 📦 快速启动
下载下方的 `Kypetz-v1.0.0-Windows.zip`，解压后双击 `start.vbs` 即可无黑框启动！
"""


def detect_local_proxy():
    """自动检测常见的本地代理端口 (Clash, v2ray 等)"""
    # 检查环境变量
    for env in ["HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY"]:
        if os.environ.get(env):
            return os.environ.get(env)

    # 探测本地端口
    common_ports = [7890, 10809, 10808, 7897, 1080]
    for port in common_ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.15)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return f"http://127.0.0.1:{port}"
    return None


def get_opener(proxy_url=None):
    """构建带代理或直连的 URL Opener"""
    if proxy_url:
        proxy_handler = urllib.request.ProxyHandler({
            "http": proxy_url,
            "https": proxy_url
        })
        return urllib.request.build_opener(proxy_handler)
    return urllib.request.build_opener()


CURRENT_PROXY = detect_local_proxy()


def github_api_request(url, method="GET", data=None, token=None, content_type="application/json"):
    headers = {
        "User-Agent": "Kypetz-Release-Bot/1.0",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if content_type:
        headers["Content-Type"] = content_type

    body_bytes = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body_bytes = json.dumps(data).encode("utf-8")
        elif isinstance(data, bytes):
            body_bytes = data
        else:
            body_bytes = str(data).encode("utf-8")

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    opener = get_opener(CURRENT_PROXY)

    try:
        with opener.open(req, timeout=120) as r:
            res_data = r.read()
            if res_data:
                try:
                    return json.loads(res_data.decode("utf-8"))
                except Exception:
                    return res_data
            return {}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        return {"_error_code": e.code, "_error_msg": err_msg}
    except Exception as e:
        return {"_error_code": -1, "_error_msg": str(e)}


def main():
    global CURRENT_PROXY
    print("=" * 65)
    print(f"  Kypetz 一键自动上传与 GitHub Release 发布工具 ({TAG_NAME})")
    print("=" * 65)

    if CURRENT_PROXY:
        print(f"[网络状态] 已自动检测并挂载本地加速代理: {CURRENT_PROXY} ✓")
    else:
        print("[网络状态] 当前为直连模式 (若连接超时建议开启网络加速软件)")

    # 1. 获取 GitHub Token
    print("\n[重要鉴权说明]：")
    print("GitHub 官方自 2021 年起已永久禁用密码登录/推送。")
    print("请使用你的 Personal Access Token (PAT，以 ghp_ 开头)。")
    print("若尚未生成，请按住 Ctrl 点击下方链接一键创建 (勾选 'repo' 权限，10 秒搞定)：")
    print("👉 https://github.com/settings/tokens/new?scopes=repo&description=Kypetz-Release\n")

    token = input("请输入你的 GitHub Token (以 ghp_ 开头): ").strip()
    if not token:
        print("[错误] 未输入有效 Token，发布已终止。")
        return

    # 2. 检查或创建仓库
    print(f"\n1. 正在检查远程仓库 https://github.com/{REPO_OWNER}/{REPO_NAME} ...")
    repo_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
    repo_info = github_api_request(repo_url, token=token)

    if "_error_code" in repo_info and repo_info["_error_code"] == 404:
        print(f"   远程仓库尚未创建，正在自动创建公开开源仓库 {REPO_OWNER}/{REPO_NAME} ...")
        create_url = "https://api.github.com/user/repos"
        create_payload = {
            "name": REPO_NAME,
            "description": "基于 Python (PySide6) 和 Live2D 的开源二次元 AI 桌面伴侣",
            "private": False,
            "has_issues": True,
            "has_wiki": True
        }
        res_create = github_api_request(create_url, method="POST", data=create_payload, token=token)
        if "_error_code" in res_create:
            print(f"   [创建仓库失败]: {res_create.get('_error_msg')}")
            return
        print(f"   ✓ 成功创建仓库: https://github.com/{REPO_OWNER}/{REPO_NAME}")
    elif "_error_code" in repo_info:
        err = repo_info.get("_error_msg", "")
        print(f"   [连接异常]: {err}")
        if "Bad credentials" in err:
            print("   👉 提示: 你的 Token 无效或已过期，请重新生成并确保勾选了 'repo' 权限。")
        elif "timed out" in err or "10054" in err or "10060" in err:
            print("   👉 提示: 国内网络访问 api.github.com 受到波动阻断，请开启代理工具 (如 Clash/v2ray) 后重试！")
        return
    else:
        print(f"   ✓ 远程仓库就绪: https://github.com/{REPO_OWNER}/{REPO_NAME}")

    # 3. 创建 Release
    print(f"\n2. 正在发布 Release 版本 {TAG_NAME} ...")
    release_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases"
    release_payload = {
        "tag_name": TAG_NAME,
        "target_commitish": "main",
        "name": RELEASE_NAME,
        "body": RELEASE_BODY,
        "draft": False,
        "prerelease": False,
        "generate_release_notes": False
    }
    rel_res = github_api_request(release_url, method="POST", data=release_payload, token=token)

    upload_url_tpl = None
    if "_error_code" in rel_res:
        if "already_exists" in str(rel_res.get("_error_msg", "")):
            print(f"   Release {TAG_NAME} 已存在，正在拉取现有 Release 资产信息...")
            get_rel_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/tags/{TAG_NAME}"
            existing_rel = github_api_request(get_rel_url, token=token)
            upload_url_tpl = existing_rel.get("upload_url")
        else:
            print(f"   [创建 Release 失败]: {rel_res.get('_error_msg')}")
            return
    else:
        print(f"   ✓ Release {TAG_NAME} 创建成功！")
        upload_url_tpl = rel_res.get("upload_url")

    # 4. 上传资产安装包
    if not os.path.exists(ZIP_PATH):
        print(f"   [警告] 找不到预打包安装包: {ZIP_PATH}")
        return

    file_size_mb = os.path.getsize(ZIP_PATH) / (1024 * 1024)
    print(f"\n3. 正在上传 Release 资产包: Kypetz-v1.0.0-Windows.zip ({file_size_mb:.2f} MB) ...")
    if upload_url_tpl:
        clean_upload_url = upload_url_tpl.split("{")[0] + "?name=Kypetz-v1.0.0-Windows.zip"
        with open(ZIP_PATH, "rb") as zf:
            zip_bytes = zf.read()

        up_res = github_api_request(
            clean_upload_url,
            method="POST",
            data=zip_bytes,
            token=token,
            content_type="application/zip"
        )
        if "_error_code" in up_res:
            print(f"   [资产上传状态]: {up_res.get('_error_msg', '')}")
        else:
            print("   ✓ 资产文件已成功挂载至 Release！")

    print("\n" + "=" * 65)
    print("🎉 全部发布成功！")
    print(f"👉 仓库主页: https://github.com/{REPO_OWNER}/{REPO_NAME}")
    print(f"👉 Release 页面: https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/tag/{TAG_NAME}")
    print("=" * 65)


if __name__ == "__main__":
    main()
