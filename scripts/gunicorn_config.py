"""
Gunicorn 配置檔 — MUSEON Gateway
用法：gunicorn -c scripts/gunicorn_config.py museon.gateway.server:app

設計原則：
- on_starting：master 進程執行 preflight + governor lock（取代 main() 的保護層）
- on_worker_exit：記錄 worker 退出
- worker_exit：Gunicorn 管理 worker 生命週期，不需要手動重啟
"""
import os
import sys
import logging

# ─── 基本設定 ───────────────────────────────────────
bind = "127.0.0.1:8765"
workers = 1  # Gateway 狀態多、不適合多 worker（brain/session 全局狀態）
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120
graceful_timeout = 30
keepalive = 5

# ─── 進程管理 ────────────────────────────────────────
preload_app = False  # 不預載，讓 worker 各自 import（避免 fork 後狀態混亂）
daemon = False        # launchd 管理，不自行 daemonize

# ─── 日誌 ────────────────────────────────────────────
loglevel = "info"
accesslog = "-"   # stdout → launchd 重導向到 gateway.log
errorlog = "-"    # stderr → launchd 重導向到 gateway.err
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(L)ss'

# ─── Gunicorn hooks ─────────────────────────────────

def on_starting(server):
    """Master 進程啟動時執行 preflight + governor（取代 main() 的保護層）"""
    # 加入 PYTHONPATH
    _runtime_src = "/Users/ZEALCHOU/MUSEON/.runtime/src"
    if _runtime_src not in sys.path:
        sys.path.insert(0, _runtime_src)

    # 確保 site-packages 可用
    _site = "/Users/ZEALCHOU/MUSEON/.runtime/.venv/lib/python3.13/site-packages"
    if _site not in sys.path:
        sys.path.insert(0, _site)

    logger = logging.getLogger("gunicorn.error")

    # ── 1. 載入 .env ──
    try:
        from museon.gateway.server import _load_env_file, _configure_logging
        _configure_logging()
        _load_env_file()
        logger.info("[on_starting] .env 載入完成")
    except Exception as e:
        logger.warning(f"[on_starting] .env 載入失敗（非致命）: {e}")

    # ── 2. PreflightGate ──
    try:
        from museon.governance.preflight import PreflightGate
        result = PreflightGate().run()
        for w in result.warnings:
            logger.warning(f"[on_starting] Preflight warning: {w}")
        if not result.passed:
            for f in result.failures:
                logger.error(f"[on_starting] Preflight FATAL: {f}")
            logger.error("[on_starting] Preflight 失敗，Gunicorn 中止啟動")
            sys.exit(1)  # Gunicorn master 退出，launchd 會依 ThrottleInterval 重試
        logger.info("[on_starting] Preflight 通過")
    except Exception as e:
        logger.warning(f"[on_starting] Preflight 檢查失敗（非致命，繼續啟動）: {e}")

    # ── 3. RefractoryGuard ──
    try:
        from museon.governance.refractory import RefractoryGuard
        refractory = RefractoryGuard()
        action, wait_secs = refractory.check()
        if action == "hibernate":
            logger.warning("[on_starting] RefractoryGuard: 休眠中，中止啟動")
            sys.exit(0)
        elif action == "backoff":
            import time
            logger.warning(f"[on_starting] RefractoryGuard: 退避 {wait_secs}s")
            time.sleep(wait_secs)
        logger.info("[on_starting] RefractoryGuard 通過")
    except Exception as e:
        logger.warning(f"[on_starting] RefractoryGuard 失敗（非致命）: {e}")


def worker_exit(server, worker):
    """Worker 退出時記錄"""
    logger = logging.getLogger("gunicorn.error")
    logger.info(f"[worker_exit] Worker PID={worker.pid} 退出")


def post_fork(server, worker):
    """Worker fork 後執行"""
    logger = logging.getLogger("gunicorn.error")
    logger.info(f"[post_fork] Worker PID={worker.pid} 已 fork")
