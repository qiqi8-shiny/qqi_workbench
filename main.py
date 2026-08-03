#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
科研通(AbleSci) 每日签到自动化脚本（Playwright 版，仅科研通）
==============================================================
登录地址 : https://www.ablesci.com/site/login  (邮箱 + 密码)
签到接口 : 登录后 GET https://www.ablesci.com/user/sign 即完成签到
           （该接口返回 JSON：code=0 签到成功；code=1 且提示已签到=今日已签过）
结果     : 写入 data/signin-status.json，供前端工作台「每日签到」读取
触发     : GitHub Actions 每天北京时间 08:00（见 .github/workflows/daily_signin.yml）
凭证     : 仅来自环境变量 KYT_USER / KYT_PASS（由仓库 Secrets 注入），不写死本文件
"""

import os
import sys
import json
import threading
from datetime import datetime, timezone, timedelta

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ 缺少依赖：pip install playwright && playwright install chromium")
    sys.exit(1)

KYT_LOGIN_URL = "https://www.ablesci.com/site/login"
KYT_SIGN_URL = "https://www.ablesci.com/user/sign"
STATUS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "signin-status.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _safe_close(obj):
    """后台线程带超时关闭 Playwright 对象，避免 close() 卡死导致进程挂起。"""
    def _c():
        try:
            obj.close()
        except Exception:
            pass
    th = threading.Thread(target=_c, daemon=True)
    th.start()
    th.join(timeout=20)


def load_status():
    try:
        with open(STATUS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_status(status):
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def kyts_signin(user, password):
    """登录科研通并调用签到接口。返回 (done: bool, note: str)。"""
    if not user or not password:
        return False, "缺少 KYT_USER / KYT_PASS 环境变量"

    result = (False, "未知错误")
    p = None
    browser = None
    try:
        p = sync_playwright().start()
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-background-networking",
                  "--disable-dev-shm-usage", "--disable-extensions"],
        )
        context = browser.new_context(user_agent=UA, locale="zh-CN")
        page = context.new_page()
        page.set_default_timeout(30000)

        print("→ 打开科研通登录页：%s" % KYT_LOGIN_URL)
        page.goto(KYT_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

        # 登录按钮是 layui 动态渲染且 JS 绑定点击，用 JS 派发 click 绕过可见性判定
        page.wait_for_selector("button[lay-filter='do-submit']", state="attached", timeout=15000)
        page.fill("#LAY-user-login-email", user)
        page.fill("#LAY-user-login-password", password)
        page.evaluate("document.querySelector(\"button[lay-filter='do-submit']\").click()")
        # 等待登录结果（layui 用 JS 跳转，成功后离开登录页）
        page.wait_for_timeout(8000)

        # 登录失败：仍停在登录页
        if "/site/login" in page.url:
            err = page.evaluate(
                "() => {"
                "  const el = document.querySelector('.layui-layer-content')"
                " || document.querySelector('.error')"
                " || document.querySelector('.layui-form-item .error')"
                " || document.querySelector('[class*=err]');"
                "  return el ? (el.innerText||'').trim().slice(0,120) : '（页面停留在登录页，可能触发了验证码/风控）';"
                "}"
            )
            return False, "登录失败：" + err
        print("✓ 登录成功")

        # 调用签到接口（GET 即签到）
        print("→ 调用签到接口：%s" % KYT_SIGN_URL)
        page.goto(KYT_SIGN_URL, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1500)
        body = page.evaluate("() => document.body.innerText").strip()
        print("  接口返回：" + body)

        try:
            data = json.loads(body)
            code = data.get("code")
            msg = data.get("msg", "")
        except Exception:
            code, msg = None, body[:120]

        if code == 0:
            result = (True, "签到成功：" + msg)
        elif code == 1 and ("已签到" in msg or "已经" in msg or "已" in msg):
            # 今日已签过，视为成功
            result = (True, "今日已签到（无需重复）：" + msg)
        else:
            result = (False, "签到接口返回异常：" + msg)
    except Exception as e:
        result = (False, "运行异常：" + str(e))
    finally:
        if browser:
            _safe_close(browser)
        if p:
            _safe_close(p)
    return result


def main():
    status = load_status()
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)

    kt_user = os.getenv("KYT_USER")
    kt_pass = os.getenv("KYT_PASS")
    kt_done, kt_note = kyts_signin(kt_user, kt_pass)
    status["keyantong"] = {
        "done": kt_done,
        "points": 10 if kt_done else 0,
        "note": kt_note,
    }
    # Workbuddy 本仓库不做自动签到，保留键位兼容前端展示为「未开启」
    status["workbuddy"] = {
        "done": False,
        "points": 0,
        "note": "未开启自动签到（Workbuddy 为手机验证码登录，未接入自动）",
    }
    status["updatedAt"] = now.isoformat()
    save_status(status)
    print("✅ 已写入状态文件：" + STATUS_PATH)
    print("   科研通 done=%s note=%s" % (kt_done, kt_note))


if __name__ == "__main__":
    main()
