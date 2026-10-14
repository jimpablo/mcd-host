# 更新日志

## 0.2.0（2026-10-14）

- `card --style receipt`：竖版热敏小票风请客方案卡（锯齿边、装饰条形码由方案内容确定性生成），适合发朋友圈/小红书；`plan --card --style` 同步支持
- `assets/demo.svg`：README 终端演示动画（打字机效果，纯 SVG + CSS，遵守 prefers-reduced-motion），由 `scripts/make_demo_svg.py` 生成
- GitHub 仓库补充 topics（mcp/mcdonalds/agent/skill/workbuddy 等）提升发现性

## 0.1.0（2026-10-14）

- 首个版本：麦门东道主 · 请客参谋
- `plan`：凑一桌引擎——套餐优先（单人随心配不算正餐）、单点兜底、预算控制、忌口过滤、必点支持、一单一张券的最优挑选与满减差额提示、人均分摊（向上取整）、人均热量估算与预警
- `card`：请客方案卡 SVG（自包含、浅色/深色自适应、无个人信息）+ 终端文字版
- `fetch`：MCP 只读数据拉取（stores/menu/coupons/nutrition），Token 支持环境变量、`.env`、配置文件三种本机存放方式
- `demo`：合成数据一键演示，不需要 Token
- 安全边界：只调用只读 MCP 工具白名单，写操作一律不碰；MCP 地址写死；Token 不进日志和仓库
- 测试：pytest 覆盖归一化、凑桌算法、卡片生成与 CLI 契约
