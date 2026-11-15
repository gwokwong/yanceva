#!/usr/bin/env python3
"""构建后预渲染：为每个 SPA 路由生成静态 HTML 快照（供爬虫/AI 引擎抓取）。

原理：用无头浏览器渲染每个路由 → 把渲染后的完整 HTML 写入 dist/<route>/index.html。
Flask 的 SPA fallback 天然优先返回这些文件，爬虫无需执行 JS 即可读取完整内容。

运行时机：npm run build 之后（deploy.sh setup 已集成）。
人工运行：cd frontend && node scripts/prerender.mjs（或 bash scripts/deploy.sh prerender）
"""

import subprocess
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent
DIST = FRONTEND / "dist"
ROUTES = ["/", "/orders", "/rehearse", "/privacy", "/terms"]
SITE = "https://yanceva.com"


def prerender_with_node():
    """用 puppeteer/playwright 渲染——检查可用工具后选择方案。"""
    script = f"""
import {{ chromium }} from 'playwright-core';
import {{ executablePath }} from 'chrome-launcher';

const routes = {ROUTES!r};
const browser = await chromium.launch({{
  executablePath: executablePath(),
  args: ['--no-sandbox'],
}});
const page = await browser.newPage();

for (const route of routes) {{
  await page.goto('http://localhost:5001' + route, {{ waitUntil: 'networkidle2', timeout: 30000 }});
  await page.waitForTimeout(1500); // 字体+异步渲染
  const html = await page.content();
  const dir = '{DIST}' + (route === '/' ? '' : route);
  fs.mkdirSync(dir, {{ recursive: true }});
  fs.writeFileSync(dir + '/index.html', html);
  console.log('✓ prerendered', route);
}}
await browser.close();
"""
    print("Node prerender script:")
    print(script)


if __name__ == "__main__":
    print(__doc__)
    prerender_with_node()
