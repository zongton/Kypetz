/* ============================================================
 * pet_loader.js — Live2D 桌面伴侣加载器与交互核心
 * 包含：Apple 极简磨砂对话框 + 官方 QtWebChannel 双向通信 + 拖拽与缩放 + 动态模型加载
 * ============================================================ */
(function () {
    "use strict";

    const Live2DModelCls =
        (window.PIXI && PIXI.live2d && PIXI.live2d.Live2DModel) ||
        window.Live2DModel;

    function abs(path) {
        return new URL(path, window.location.href).href;
    }

    // ---- 通用 Live2D 模型路径与配置文件动态解析器 ----
    function resolveModelUrl(modelPath) {
        if (!modelPath) return abs("./live2d-model/rana/038_collabo_a_ur/index.json");
        let p = String(modelPath).trim().replace(/\\/g, "/");

        // 1. 若是绝对 HTTP 路径直接返回
        if (p.startsWith("http://") || p.startsWith("https://")) {
            return p.endsWith(".json") ? p : p.replace(/\/+$/, "") + "/index.json";
        }

        // 2. 去除前导 ./ 或 /
        p = p.replace(/^\.?\/+/, "");

        // 3. 智能自适应前缀路径
        if (p.startsWith("live2d-model/")) {
            // 已有标准相对目录
        } else if (p.startsWith("rana/")) {
            p = "live2d-model/" + p;
        } else if (!p.startsWith("../")) {
            if (p.startsWith("038_")) {
                p = "live2d-model/rana/" + p;
            } else {
                p = "live2d-model/" + p;
            }
        }

        // 4. 确保定位到描述文件
        if (!p.endsWith(".json")) {
            p = p.replace(/\/+$/, "") + "/index.json";
        }

        return abs(p);
    }

    function _esc(s) {
        return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    let model = null;
    let app = null;

    // ---- 动作、表情、口型 API (预先初始化，防止未定义) ----
    window.setExpression = function (name) {
        if (!model) return;
        try {
            if (model.expression) model.expression(name);
        } catch (e) {
            console.warn("[pet_loader] expression err", e);
        }
    };

    let actionLockTimer = null;
    window.isPerformingAction = false;

    window.setMotion = function (name, priority, lockMs) {
        if (!model) return;
        try {
            const prio = (priority !== undefined) ? priority : 3;
            model.motion(name, 0, prio);
            window.isPerformingAction = true;
            if (actionLockTimer) clearTimeout(actionLockTimer);
            const lockTime = lockMs || 3500;
            actionLockTimer = setTimeout(function () {
                window.isPerformingAction = false;
            }, lockTime);
        } catch (e) {
            console.warn("[pet_loader] motion err", e);
        }
    };

    window.setMouthOpen = function (v) {
        try {
            if (model && model.internalModel && model.internalModel.parameter) {
                model.internalModel.parameter.values["ParamMouthOpenY"] = Number(v) || 0;
            }
        } catch (e) { }
    };

    window.performAction = function (mot, exp, durationMs) {
        try {
            if (exp && window.setExpression) window.setExpression(exp);
            if (mot && window.setMotion) {
                const lockDur = durationMs ? Math.min(8000, durationMs + 600) : 3500;
                window.setMotion(mot, 3, lockDur);
            }
            console.log("[pet_loader] 执行动作:", mot, "表情:", exp);
        } catch (e) {
            console.warn("[pet_loader] 动作执行失败:", e);
        }
    };

    // ---- 初始化函数 (UI 与通信绝对先行，绝不受模型加载影响) ----
    async function init() {
        // ============================================================
        // 1. UI 界面层构建：回复对话框、用户气泡、输入抽屉
        // ============================================================
        var ranaCard = document.createElement("div");
        ranaCard.id = "rana-reply-card";
        ranaCard.style.cssText =
            "position: fixed; left: 16px; right: 16px; top: 28px; " +
            "padding: 14px 18px; border-radius: 20px; " +
            "background: rgba(22, 22, 28, 0.90); " +
            "backdrop-filter: blur(28px) saturate(190%); -webkit-backdrop-filter: blur(28px) saturate(190%); " +
            "border: 1px solid rgba(255, 255, 255, 0.18); " +
            "box-shadow: 0 16px 48px rgba(0, 0, 0, 0.48), 0 2px 8px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.22); " +
            "opacity: 0; transform: translateY(-12px) scale(0.96); " +
            "transition: opacity 0.35s cubic-bezier(0.16, 1, 0.3, 1), transform 0.35s cubic-bezier(0.16, 1, 0.3, 1); " +
            "pointer-events: auto; user-select: text; z-index: 10000; " +
            "font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'PingFang SC', 'Microsoft YaHei UI', sans-serif;";
        document.body.appendChild(ranaCard);

        var _ranaTimer = null;
        window.showRanaBubble = function (text, durationMs, petName) {
            if (!ranaCard || !text) return;
            // 前端双重保险：彻底抹去任何机器指令标签 [action: ...]
            var cleanText = String(text || "").replace(/\[(?:action|motion|expression)\s*:[^\]]*\]/gi, "").trim();
            if (!cleanText) return;
            var name = petName || "桌宠";
            ranaCard.innerHTML =
                "<div style='display:flex; align-items:center; margin-bottom:8px;'>" +
                "  <span style='display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px; border-radius:11px; background:rgba(133,227,179,0.18); margin-right:8px;'>" +
                "    <svg width='13' height='13' viewBox='0 0 24 24' fill='none' stroke='#85E3B3' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='m19 5-3 3M14 10l-1.5 1.5M10.5 13.5 9 15M2 22l6.5-6.5a4.5 4.5 0 0 0 6.36-6.36L22 2l-7 7.14a4.5 4.5 0 0 0-6.36 6.36L2 22z'/><circle cx='12' cy='12' r='1.5' fill='#85E3B3'/></svg>" +
                "  </span>" +
                "  <span style='font-size:13px; font-weight:600; color:#85E3B3; letter-spacing:0.3px;'>" + _esc(name) + "</span>" +
                "  <span style='margin-left:auto; cursor:pointer; opacity:0.4; font-size:12px;' onclick='this.closest(\"#rana-reply-card\").style.opacity=0;'>✕</span>" +
                "</div>" +
                "<div style='color:rgba(255,255,255,0.96); font-size:14.5px; font-weight:400; line-height:1.65; word-break:break-word;'>" +
                _esc(cleanText) +
                "</div>";
            ranaCard.style.opacity = "1";
            ranaCard.style.transform = "translateY(0) scale(1)";
            if (_ranaTimer) clearTimeout(_ranaTimer);
            var keepTime = durationMs ? Math.max(5000, durationMs + 2500) : 12000;
            _ranaTimer = setTimeout(function () {
                ranaCard.style.opacity = "0";
                ranaCard.style.transform = "translateY(-12px) scale(0.96)";
            }, keepTime);
        };

        var userCard = document.createElement("div");
        userCard.id = "rana-user-bubble";
        userCard.style.cssText =
            "position: fixed; right: 16px; bottom: 114px; max-width: 82%; " +
            "padding: 9px 15px; border-radius: 17px; " +
            "background: rgba(10, 132, 255, 0.92); " +
            "backdrop-filter: blur(28px) saturate(190%); -webkit-backdrop-filter: blur(28px) saturate(190%); " +
            "box-shadow: 0 12px 36px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.35); " +
            "opacity: 0; transform: translateY(8px) scale(0.96); " +
            "transition: opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1), transform 0.3s cubic-bezier(0.16, 1, 0.3, 1); " +
            "pointer-events: auto; user-select: text; z-index: 10000; " +
            "font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'PingFang SC', 'Microsoft YaHei UI', sans-serif;";
        document.body.appendChild(userCard);

        var _userTimer = null;
        window.showUserBubble = function (text, userCall) {
            if (!userCard || !text) return;
            var call = userCall || "你";
            userCard.innerHTML =
                "<div style='font-size:11px; font-weight:600; color:rgba(255,255,255,0.75); margin-bottom:3px;'>" + _esc(call) + "</div>" +
                "<div style='color:#FFFFFF; font-size:13.5px; font-weight:500; line-height:1.5; word-break:break-word;'>" + _esc(text) + "</div>";
            userCard.style.opacity = "1";
            userCard.style.transform = "translateY(0) scale(1)";
            if (_userTimer) clearTimeout(_userTimer);
            _userTimer = setTimeout(function () {
                userCard.style.opacity = "0";
                userCard.style.transform = "translateY(8px) scale(0.96)";
            }, 8000);
        };

        // 灵动打字输入抽屉
        var inputDrawer = document.createElement("div");
        inputDrawer.id = "rana-apple-input";
        inputDrawer.style.cssText =
            "position: fixed; left: 16px; right: 16px; bottom: 58px; " +
            "padding: 5px 6px 5px 16px; border-radius: 20px; " +
            "background: rgba(26, 26, 32, 0.95); " +
            "backdrop-filter: blur(28px) saturate(190%); -webkit-backdrop-filter: blur(28px) saturate(190%); " +
            "border: 1px solid rgba(255, 255, 255, 0.24); " +
            "box-shadow: 0 16px 45px rgba(0, 0, 0, 0.6), 0 2px 8px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.25); " +
            "display: flex; align-items: center; gap: 8px; " +
            "opacity: 0; transform: translateY(12px) scale(0.96); pointer-events: none; " +
            "transition: opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1), transform 0.3s cubic-bezier(0.16, 1, 0.3, 1); " +
            "z-index: 999999; font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'PingFang SC', 'Microsoft YaHei UI', sans-serif;";

        inputDrawer.innerHTML =
            "<input id='rana-quick-edit' placeholder='键入消息并发送…' " +
            "  style='flex:1; background:transparent; border:none; outline:none; color:#FFFFFF; font-size:13.5px; padding:6px 0;' />" +
            "<button id='rana-quick-send' " +
            "  style='background:#0071E3; color:#FFFFFF; border:none; border-radius:15px; padding:6px 14px; font-size:12.5px; font-weight:600; cursor:pointer; transition:background .2s;'>" +
            "  发送" +
            "</button>" +
            "<button id='rana-quick-close' " +
            "  style='background:rgba(255,255,255,0.1); color:rgba(255,255,255,0.7); border:none; border-radius:15px; width:28px; height:28px; font-size:12px; cursor:pointer; display:flex; align-items:center; justify-content:center;'>" +
            "  ✕" +
            "</button>";

        document.body.appendChild(inputDrawer);

        var editEl = document.getElementById("rana-quick-edit");
        var sendBtn = document.getElementById("rana-quick-send");
        var closeBtn = document.getElementById("rana-quick-close");

        function doSendText() {
            var val = (editEl.value || "").trim();
            if (val) {
                editEl.value = "";
                window.showUserBubble(val);
                if (window._bridge && window._bridge.send_user_text) {
                    console.log("[pet_loader] 正在向 Python 发送消息:", val);
                    window._bridge.send_user_text(val);
                } else {
                    console.warn("[pet_loader] _bridge 未就绪，正在尝试重连通信通道...");
                    setupWebChannel();
                    setTimeout(function () {
                        if (window._bridge && window._bridge.send_user_text) {
                            window._bridge.send_user_text(val);
                        }
                    }, 200);
                }
                // 发送后自动折叠输入框
                if (window.toggleInput) {
                    setTimeout(function () { window.toggleInput(); }, 180);
                }
            }
        }

        sendBtn.addEventListener("click", doSendText);
        editEl.addEventListener("keydown", function (e) {
            if (e.key === "Enter") doSendText();
        });

        window.toggleInput = function () {
            var isShown = inputDrawer.style.opacity === "1";
            if (isShown) {
                inputDrawer.style.opacity = "0";
                inputDrawer.style.transform = "translateY(12px) scale(0.96)";
                inputDrawer.style.pointerEvents = "none";
            } else {
                inputDrawer.style.opacity = "1";
                inputDrawer.style.transform = "translateY(0) scale(1)";
                inputDrawer.style.pointerEvents = "auto";
                setTimeout(function () { editEl.focus(); }, 60);
            }
            return !isShown;
        };

        closeBtn.addEventListener("click", function () {
            window.toggleInput();
        });

        // ============================================================
        // 2. 官方 QtWebChannel 可靠初始化 (带持续轮询，确保 100% 连上)
        // ============================================================
        let channelRetryCount = 0;
        function setupWebChannel() {
            if (window.QWebChannel && window.qt && qt.webChannelTransport) {
                new QWebChannel(qt.webChannelTransport, function (channel) {
                    window._bridge = channel.objects.bridge;
                    console.log("[pet_loader] Qt WebChannel 已成功连接 ✓");
                });
            } else {
                if (channelRetryCount < 80) {
                    channelRetryCount++;
                    setTimeout(setupWebChannel, 80);
                }
            }
        }
        setupWebChannel();

        // ============================================================
        // 3. PIXI 画布创建与模型加载沙箱
        // ============================================================
        const canvas = document.getElementById("live2d");
        if (!canvas) throw new Error("找不到 #live2d 画布");

        app = new PIXI.Application({
            view: canvas,
            autoStart: true,
            backgroundAlpha: 0,
            antialias: true,
            resolution: window.devicePixelRatio || 1,
            autoDensity: true,
        });

        // 视口自适应居中与防循环缩放计算 (严格基于原始未缩放设计尺寸)
        window._ranaOffsetX = 0;
        window._ranaOffsetY = 0;
        window._ranaUserScale = 1.0;

        function fit() {
            if (!model) return;
            const w = window.innerWidth || document.documentElement.clientWidth || 340;
            const h = window.innerHeight || document.documentElement.clientHeight || 500;
            app.renderer.resize(w, h);

            // 锁定原始模型未经 scale 变换的设计宽高，彻底根除缩放循环放大/缩小 Bug
            if (!model.rawModelWidth || model.rawModelWidth <= 0) {
                model.rawModelWidth = (model.internalModel && model.internalModel.width) || 800;
                model.rawModelHeight = (model.internalModel && model.internalModel.height) || 1000;
            }
            const origW = model.rawModelWidth;
            const origH = model.rawModelHeight;

            const scaleX = (w * 0.94) / origW;
            const scaleY = (h * 0.94) / origH;
            const baseScale = Math.min(scaleX, scaleY);
            const userScale = Math.max(0.25, Math.min(window._ranaUserScale || 1.0, 4.0));
            const finalScale = baseScale * userScale;

            model.scale.set(finalScale);

            const actualW = origW * finalScale;
            const actualH = origH * finalScale;
            model.x = (w - actualW) / 2 + (window._ranaOffsetX || 0);
            model.y = (h - actualH) / 2 + (window._ranaOffsetY || 0);
        }
        window.addEventListener("resize", fit);

        window.setRanaScale = function (factor) {
            const current = window._ranaUserScale || 1.0;
            window._ranaUserScale = Math.max(0.25, Math.min(current * factor, 4.0));
            console.log("[pet_loader] 角色缩放比例调节为:", (window._ranaUserScale * 100).toFixed(0) + "%");
            fit();
            return window._ranaUserScale;
        };

        window.resetRanaScale = function () {
            window._ranaUserScale = 1.0;
            window._ranaOffsetX = 0;
            window._ranaOffsetY = 0;
            console.log("[pet_loader] 角色缩放与位置已重置 1:1");
            fit();
            return 1.0;
        };

        // 待机循环
        let lastMotion = null;
        function playIdle() {
            if (!model || window.isPerformingAction) return;
            try {
                const mm = model.internalModel && model.internalModel.motionManager;
                if (mm && mm.isFinished()) {
                    model.motion("idle01", 0, 1);
                } else if (mm === undefined && lastMotion !== "idle01") {
                    model.motion("idle01", 0, 1);
                    lastMotion = "idle01";
                }
            } catch (e) { }
        }
        window.setInterval(playIdle, 300);

                async function loadModelByDir(modelDir) {
            let indexUrl = resolveModelUrl(modelDir);
            console.log("[pet_loader] 正在加载 Live2D 描述文件 ->", indexUrl);

            // 1. 优先使用 pixi-live2d-display 官方全通用加载器 (原生自动识别 Cubism 2 / 3 / 4 / 5)
            let newModel = null;
            try {
                newModel = await Live2DModelCls.from(indexUrl, { autoInteract: true, motionPreload: true });
            } catch (errFromUrl) {
                console.warn("[pet_loader] 直接 URL 原生加载遇阻，进入自适应回退流水线:", errFromUrl);

                let resp = await fetch(indexUrl);
                if (!resp.ok && indexUrl.endsWith("/index.json")) {
                    let fallbackUrl = indexUrl.replace(/\/index\.json$/, "/model.json");
                    let r2 = await fetch(fallbackUrl);
                    if (r2.ok) {
                        indexUrl = fallbackUrl;
                        resp = r2;
                    }
                }
                if (!resp.ok) {
                    throw new Error("无法加载模型描述文件 (HTTP " + resp.status + "): " + indexUrl);
                }

                const index = await resp.json();
                const baseDir = indexUrl.substring(0, indexUrl.lastIndexOf("/") + 1);

                // 兼顾 Cubism 2 与 Cubism 3/4 FileReferences 结构
                const fileRefs = index.FileReferences || {};
                const mocFile = index.model || fileRefs.Moc || "";
                const poseFile = index.pose || fileRefs.Pose;
                const physicsFile = index.physics || fileRefs.Physics;
                const rawTextures = index.textures || fileRefs.Textures || [];
                const rawMotions = index.motions || fileRefs.Motions || {};
                const rawExps = index.expressions || fileRefs.Expressions || [];

                const settings = {
                    url: indexUrl,
                    model: abs(baseDir + mocFile),
                    pose: poseFile ? abs(baseDir + poseFile) : undefined,
                    physics: physicsFile ? abs(baseDir + physicsFile) : undefined,
                    layout: index.layout || undefined,
                    hit_areas: index.hit_areas || fileRefs.HitAreas || undefined,
                    textures: rawTextures.map(function (t) { return abs(baseDir + t); }),
                    motions: {},
                    expressions: rawExps.map(function (e) {
                        return { name: e.name || e.Name, file: abs(baseDir + (e.file || e.File)) };
                    }),
                };
                for (const name in rawMotions) {
                    const mList = Array.isArray(rawMotions[name]) ? rawMotions[name] : [rawMotions[name]];
                    settings.motions[name] = mList.map(function (m) {
                        return { file: abs(baseDir + (m.file || m.File)) };
                    });
                }
                if (!settings.motions.idle && settings.motions.idle01) {
                    settings.motions.idle = settings.motions.idle01;
                }

                newModel = await Live2DModelCls.from(settings, { motionPreload: true });
            }

            if (model && model.parent) {
                model.parent.removeChild(model);
                try { model.destroy(); } catch (e) {}
            }
            model = newModel;
            app.stage.addChild(model);
            window.__ranaModel = model;
            fit();

            // 触发初始待机动作并由 pose.json 进行肢体互斥校准
            try { model.motion("idle", 0, 1); } catch (e) {
                try { model.motion("idle01", 0, 1); } catch (e2) {}
            }

            // 部件互斥初始状态校准
            try {
                if (model.internalModel && model.internalModel.coreModel) {
                    const core = model.internalModel.coreModel;
                    if (typeof core.getPartsDataIndex === "function" && typeof core.setPartsOpacity === "function") {
                        const armPartToHide = core.getPartsDataIndex("PARTS_01_ARM_L_01");
                        const armPartToHideR = core.getPartsDataIndex("PARTS_01_ARM_R_01");
                        if (armPartToHide >= 0) core.setPartsOpacity(armPartToHide, 0);
                        if (armPartToHideR >= 0) core.setPartsOpacity(armPartToHideR, 0);
                    }
                }
            } catch (pErr) { }

            console.log("[pet_loader] 形象加载成功，适配全部 Live2D 规范 ✓");
            return model;
        }

        window.changeModel = async function (modelKey) {
            try {
                console.log("[pet_loader] 收到换装请求 ->", modelKey);
                await loadModelByDir(modelKey);
                return true;
            } catch (e) {
                console.error("[pet_loader] 换装执行失败:", e);
                return false;
            }
        };

        // 异步安全加载初始形象 (模型异常不阻塞 UI)
        try {
            var initialModel = new URLSearchParams(location.search).get("model");
            await loadModelByDir(initialModel);
        } catch (err) {
            console.error("[pet_loader] 初始模型加载出现异常 (UI不受影响):", err);
        }

        // 自由拖拽与滚轮缩放监听
        (function () {
            var startPos = null;
            var isDragging = false;

            function isInteractive(t) {
                return t && t.closest && t.closest(
                    "input, button, textarea, #rana-reply-card, #rana-user-bubble, #rana-apple-input, a"
                );
            }

            document.addEventListener("mousedown", function (e) {
                if (e.button !== 0) return;
                if (isInteractive(e.target)) return;
                startPos = { x: e.screenX, y: e.screenY };
                isDragging = false;

                function onMouseMove(ev) {
                    if (!startPos) return;
                    var dx = ev.screenX - startPos.x;
                    var dy = ev.screenY - startPos.y;
                    if (!isDragging && Math.hypot(dx, dy) < 4) return;
                    isDragging = true;
                    startPos = { x: ev.screenX, y: ev.screenY };
                    if (window._bridge && window._bridge.move_by) {
                        window._bridge.move_by(dx, dy);
                    }
                }

                function onMouseUp() {
                    startPos = null;
                    isDragging = false;
                    document.removeEventListener("mousemove", onMouseMove);
                    document.removeEventListener("mouseup", onMouseUp);
                }

                document.addEventListener("mousemove", onMouseMove);
                document.addEventListener("mouseup", onMouseUp);
            });
        })();

        // ---- 全局视线与头部灵动追踪 (眼神注视鼠标) ----
        window.addEventListener("pointermove", function (e) {
            if (model && typeof model.focus === "function") {
                model.focus(e.clientX, e.clientY);
            }
        });

        document.addEventListener("mouseleave", function () {
            if (model && typeof model.focus === "function") {
                const w = window.innerWidth || 340;
                const h = window.innerHeight || 500;
                model.focus(w / 2, h / 2);
            }
        });

        document.addEventListener("wheel", function (e) {
            if (e.target && e.target.closest && e.target.closest("textarea, input")) return;
            e.preventDefault();
            var factor = e.deltaY < 0 ? 1.07 : 0.93;
            if (window.setRanaScale) window.setRanaScale(factor);
        }, { passive: false });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            init().catch(function (e) { console.error("[pet_loader] 初始化失败:", e); });
        });
    } else {
        init().catch(function (e) { console.error("[pet_loader] 初始化失败:", e); });
    }
})();
