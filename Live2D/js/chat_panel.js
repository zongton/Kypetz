/* ============================================================
 * chat_panel.js — 要乐奈 AI 驾驶员控制台 (Apple 风格打磨版)
 * 文字对话 → 情绪识别 → 表情/动作/嘴形联动
 * ============================================================ */
(function () {
    "use strict";
    const NOCHAT = location.search.indexOf("nochat=1") >= 0;

    // ---------- UI (Apple 极简磨砂质感) ----------
    const ui = document.createElement("div");
    ui.innerHTML = `
    <style>
      #rana-console {
        position: fixed; right: 14px; bottom: 14px; width: 310px; z-index: 99999;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Microsoft YaHei UI", sans-serif;
        user-select: none;
      }
      #rana-console .box {
        background: rgba(28, 28, 34, 0.82);
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: 18px;
        padding: 12px 14px;
        backdrop-filter: blur(24px) saturate(180%);
        -webkit-backdrop-filter: blur(24px) saturate(180%);
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.16);
      }
      #rana-console .msgs {
        height: 140px; overflow-y: auto; color: #FFFFFF; font-size: 12.5px;
        line-height: 1.6; margin-bottom: 10px; padding-right: 4px;
      }
      #rana-console .msgs::-webkit-scrollbar { width: 4px; }
      #rana-console .msgs::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 4px; }
      #rana-console .msgs .u { color: rgba(255,255,255,0.85); margin-bottom: 4px; }
      #rana-console .msgs .u b { color: rgba(255,255,255,0.6); font-weight: 500; }
      #rana-console .msgs .a { color: #FFFFFF; margin-bottom: 6px; }
      #rana-console .msgs .a b { color: #85E3B3; font-weight: 600; }
      #rana-console .row { display: flex; gap: 8px; }
      #rana-console input {
        flex: 1; border: 1px solid rgba(255, 255, 255, 0.16); border-radius: 12px;
        padding: 7px 12px; font-size: 13px; background: rgba(255, 255, 255, 0.08);
        color: #fff; outline: none; transition: border-color .2s, background .2s;
      }
      #rana-console input:focus {
        border-color: #0071E3; background: rgba(255, 255, 255, 0.12);
      }
      #rana-console button {
        border: none; border-radius: 12px; padding: 7px 14px; font-size: 13px; font-weight: 500;
        background: #0071E3; color: #fff; cursor: pointer; transition: background .2s, transform .1s;
      }
      #rana-console button:hover { background: #0077ED; }
      #rana-console button:active { transform: scale(0.96); }
      #rana-console .quick { margin-top: 8px; display: flex; gap: 5px; flex-wrap: wrap; }
      #rana-console .quick button {
        background: rgba(255, 255, 255, 0.1); font-size: 11px; padding: 3px 9px;
        border-radius: 10px; color: rgba(255,255,255,0.85); font-weight: 400;
      }
      #rana-console .quick button:hover { background: rgba(255, 255, 255, 0.18); }
    </style>
    <div id="rana-console">
      <div class="box">
        <div class="msgs" id="rana-msgs"></div>
        <div class="row">
          <input id="rana-input" placeholder="打字与乐奈对话…" />
          <button id="rana-send">发送</button>
        </div>
        <div class="quick" id="rana-quick"></div>
      </div>
    </div>`;
    document.body.appendChild(ui);
    if (NOCHAT) { ui.style.display = "none"; }

    const input = document.getElementById("rana-input");
    const msgs = document.getElementById("rana-msgs");
    const quick = document.getElementById("rana-quick");
    const sendBtn = document.getElementById("rana-send");

    function msg(role, text) {
        const div = document.createElement("div");
        div.className = role;
        div.innerHTML = (role === "u" ? "<b>你</b>: " : "<b>乐奈</b>: ") + escapeHtml(text);
        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;
    }
    function escapeHtml(s) {
        return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // ---------- 情绪与动作映射 (AI 全面操控 Live2D 模型动作) ----------
    const EMOTION_MAP = [
        { keys: ["吉他", "弹", "拿起吉他", "演奏", "琴", "弦", "弹奏", "演出", "live"], exp: "default", mot: "kime01" },
        { keys: ["歪头", "思考", "想", "为什么", "疑惑", "不解", "侧头", "低头"], exp: "thinking01", mot: "thinking01" },
        { keys: ["脸红", "害羞", "羞", "别过头", "扭过头", "娇", "笨蛋"], exp: "shame01", mot: "shame01" },
        { keys: ["坏笑", "猫笑", "猫", "喵", "小得意", "得意", "狡黠"], exp: "niya01", mot: "niya01" },
        { keys: ["笑", "微笑", "开心", "哈哈哈", "好耶", "高兴", "满意"], exp: "smile01", mot: "smile01" },
        { keys: ["生气", "鼓嘴", "怒", "瞪", "可恶", "气死", "哼"], exp: "angry01", mot: "angry01" },
        { keys: ["叹气", "哈欠", "累", "困", "睡觉", "无聊", "趴"], exp: "sigh01", mot: "sigh01" },
        { keys: ["认真", "严肃", "凝视", "盯", "注视", "比赛"], exp: "serious01", mot: "serious01" },
        { keys: ["惊讶", "哇", "愣", "卧槽", "不会吧", "睁大"], exp: "surprised01", mot: "surprised01" },
        { keys: ["再见", "拜拜", "挥手", "晚安", "走了", "下次见"], exp: "bye01", mot: "bye01" },
        { keys: ["哭", "难过", "委屈", "呜呜", "流泪"], exp: "cry01", mot: "cry01" },
        { keys: ["看", "望", "抬头", "听", "靠近"], exp: "default", mot: "idle01" },
    ];

    function actByEmotion(text) {
        for (const rule of EMOTION_MAP) {
            for (const k of rule.keys) {
                if (text.includes(k)) {
                    try { window.setExpression(rule.exp); } catch (e) {}
                    try { window.setMotion(rule.mot); } catch (e) {}
                    return;
                }
            }
        }
    }

    let mouthTimer = null;
    function talkMouth(durationMs) {
        if (mouthTimer) clearInterval(mouthTimer);
        let t = 0;
        mouthTimer = setInterval(function () {
            const v = 0.25 + 0.5 * Math.abs(Math.sin(t));
            try { window.setMouthOpen(v); } catch (e) {}
            t += 0.6;
        }, 90);
        setTimeout(function () {
            clearInterval(mouthTimer);
            try { window.setMouthOpen(0); } catch (e) {}
        }, durationMs);
    }

    window.onExternalReply = function (text, durationMs) {
        if (!NOCHAT) msg("a", text);
        actByEmotion(text);
        const dur = durationMs || Math.min(8000, Math.max(1200, (text || "").length * 280));
        talkMouth(dur);
    };

    window.showUserMsg = function (text) {
        if (!NOCHAT) msg("u", text);
    };
})();
