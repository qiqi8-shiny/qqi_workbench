#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日签到自动化脚本（Playwright 版）
====================================
目标平台：
  1. Workbuddy  （工作台，签到 +100 积分）
  2. 科研通 Keyan Tong（每日签到）

安全约定：
  - 所有账号密码 ONLY 来自环境变量，绝不写死在本文件：
      WB_USER / WB_PASS  —— Workbuddy 账号密码
      KYT_USER / KYT_PASS —— 科研通账号密码
  - 由 GitHub Actions 每天北京时间 08:00 自动运行（见 .github/workflows/daily_signin.yml）
  - 运行结果写入 data/signin-status.json，供前端工作台「每日签到」页面读取展示

⚠️ 重要（请先阅读）：
  下方 CONFIG 中的「登录地址」与「元素选择器(selector)」是占位符，
  因为不同网站的页面结构不同，我无法在不知情的情况下猜出真实选择器。
  脚本的「流程骨架 / 凭证读取 / 状态写入 / 日志输出」均已完整可用，
  但你需把 CONFIG 里标 ← 的字段替换成两个平台真实的登录页地址与签到按钮选择器，
  脚本才能真正完成签到。替换后把真实值告诉我，我也可以帮你直接填好。
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ 缺少依赖：请先执行  pip install playwright && playwright install chromium")
    sys.exit(1)


# ============================ 可配置项（请填入真实值） ============================
CONFIG = {
    "workbuddy": {
        "login_url": "https://YOUR_WORKBUDDY_DOMAIN/login",          # ← 替换为 Workbuddy 登录页地址
        "signin_url": "",                                            # ← 若签到在独立页面，填地址；否则留空（登录后同页签到）
        "user_selector": "input[name='username'], input[type='email']",
        "pass_selector": "input[name='password'], input[type='password']",
        "submit_selector": "button[type='submit'], .login-btn",
        "signed_selector": ".signin-done, text=今日已签到",          # ← 已签到后的页面标识
        "do_signin_selector": ".signin-btn, text=签到",              # ← 点击「签到」的按钮
        "points": 100,                                               # 签到成功奖励积分
    },
    "keyantong": {
        "login_url": "https://YOUR_KEYANTONG_DOMAIN/login",          # ← 替换为科研通登录页地址
        "signin_url": "",
        "user_selector": "input[name='username'], input[type='email']",
        "pass_selector": "input[name='password'], input[type='password']",
        "submit_selector": "button[type='submit'], .login-btn",
        "signed_selector": ".signed, text=今日已签到",
        "do_signin_selector": ".checkin-btn, text=签到",
        "points": 0,
    },
}
# ===========================================================================================

STATUS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "signin-status.json")


def load_status():
    if os.path.exists(STATUS_PATH):
        try:
            with open(STATUS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_status(status):
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def signin_one(name, cfg, user, password):
    """对单个平台执行登录 + 签到。返回 (done: bool, note: str)。"""
    if not user or not password:
        return False, "缺少账号/密码环境变量（%s）" % name

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            print("→ [%s] 打开登录页：%s" % (name, cfg["login_url"]))
            page.goto(cfg["login_url"], wait_until="networkidle", timeout=30000)

            page.fill(cfg["user_selector"], user)
            page.fill(cfg["pass_selector"], password)
            page.click(cfg["submit_selector"])
            page.wait_for_timeout(3000)  # 等待登录跳转

            # 若签到在独立页面，跳过去
            if cfg.get("signin_url"):
                page.goto(cfg["signin_url"], wait_until="networkidle", timeout=30000)

            # 先判断是否已签到（避免重复签到报错）
            if page.locator(cfg["signed_selector"]).count() > 0:
                return True, "今日已签到（无需重复）"

            # 点击签到按钮
            page.click(cfg["do_signin_selector"])
            page.wait_for_timeout(2000)

            done = page.locator(cfg["signed_selector"]).count() > 0
            return done, ("签到成功" if done else "点击后未检测到成功标识，请检查选择器")
        except Exception as e:
            return False, "运行异常：" + str(e)
        finally:
            browser.close()


def main():
    status = load_status()
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)

    # ---------- Workbuddy ----------
    wb_user = os.getenv("WB_USER")
    wb_pass = os.getenv("WB_PASS")
    wb_done, wb_note = signin_one("workbuddy", CONFIG["workbuddy"], wb_user, wb_pass)
    status["workbuddy"] = {
        "done": wb_done,
        "points": CONFIG["workbuddy"]["points"] if wb_done else 0,
        "note": wb_note,
    }
    if wb_done:
        print("Workbuddy 今日签到成功，+100积分")
    else:
        print("Workbuddy 今日签到失败：" + wb_note)

    # ---------- 科研通 ----------
    kt_user = os.getenv("KYT_USER")
    kt_pass = os.getenv("KYT_PASS")
    kt_done, kt_note = signin_one("keyantong", CONFIG["keyantong"], kt_user, kt_pass)
    status["keyantong"] = {
        "done": kt_done,
        "points": CONFIG["keyantong"]["points"] if kt_done else 0,
        "note": kt_note,
    }
    if kt_done:
        print("科研通今日签到成功")
    else:
        print("科研通今日签到失败：" + kt_note)

    status["updatedAt"] = now.isoformat()
    save_status(status)
    print("✅ 已写入状态文件：" + STATUS_PATH)


if __name__ == "__main__":
    main()
