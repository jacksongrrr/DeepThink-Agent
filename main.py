"""
本地启动入口：配置好 `.env` 后执行 `python main.py` 即可启动站点。

推荐：先在项目根目录执行 `pip install -e .`，再运行本脚本（亦可仅依赖下方 src 注入）。
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def main() -> None:
    import uvicorn

    from deepthink_agent.config import get_settings

    settings = get_settings()
    url = f"http://{settings.host}:{settings.port}/"
    print(f"DeepThink Agent 启动中：{url}")
    try:
        webbrowser.open(url)
    except OSError:
        pass
    uvicorn.run(
        "deepthink_agent.web.app:app",
        host=settings.host,
        port=settings.port,
        factory=False,
        reload=False,
    )


if __name__ == "__main__":
    main()
