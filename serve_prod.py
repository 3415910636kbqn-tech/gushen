"""股神生产模式启动入口：后端 API + 托管构建好的前端页面（单端口，默认 8000）
用法:
  env\Scripts\python.exe serve_prod.py          # 默认端口 8000
  set PORT=8001 && env\Scripts\python.exe serve_prod.py   # 自定义端口
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.main import app

_DIST = os.path.join(_ROOT, "frontend", "dist")

# 1) 移除主应用返回 JSON 的根路由 ("/" -> TradingAgents-CN API 信息)，
#    让前端页面接管首页
for i, route in enumerate(app.router.routes):
    path = getattr(route, "path", None)
    methods = getattr(route, "methods", None) or set()
    if path == "/" and "GET" in methods:
        del app.router.routes[i]
        print(f"[serve_prod] 已移除 API 根路由 (index {i})")
        break

# 2) SPA 兜底：静态文件存在则返回文件，否则返回 index.html（支持前端路由）
if os.path.isdir(_DIST):
    _index = os.path.join(_DIST, "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str):
        candidate = os.path.join(_DIST, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_index)

    print(f"[serve_prod] 前端已挂载: {_DIST}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")