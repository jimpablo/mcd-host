# workbuddy.md — 使用 WorkBuddy 开发的对话上下文

> 麦当劳程序员节创意开发大赛 · WorkBuddy 联动奖励核验文件
> 本项目（mcd-host · 麦门东道主）**全程在 WorkBuddy 中开发**：需求讨论、方案设计、编码、调试、对接麦当劳 MCP、提交仓库与报名，均在本对话会话中完成。以下为关键对话节点与工作记录，由 WorkBuddy 整理导出，供核验联动奖励条件。

## 会话时间线

| 阶段 | 用户指令（原文大意） | WorkBuddy 执行的关键动作 |
|---|---|---|
| 1. 调研 | 「全面了解下 mcd-developer-innovation-challenge、mcd-git 还有这个比赛，我打算参加下」 | 读取官方活动仓库（README/activityGuidelines/RANKING/CONTEST_DECLARATION）、mcd-git 参赛作品源码、麦当劳 MCP Server 文档；输出比赛规则、时间线（10/25 截止）、排名机制（纯 Star）、奖励与参赛文件清单 |
| 2. 定方向 | 「你帮我参加下吧，需要我操作的告诉我」 | 确认环境（gh 已登录 jimpablo、git/Python/Node 就绪）；调研榜单同质化情况（省钱/卡路里/MBTI 类已饱和），提供三个差异化方向，用户选定「麦门东道主 · 请客参谋」 |
| 3. 搭骨架 | 「请继续执行任务」 | 创建 mcd-host 项目：src-layout、pyproject、LICENSE、.gitignore；逐字复制官方 CONTEST_DECLARATION.md |
| 4. 核心开发 | — | 实现 model（MCP 返回值归一化）、planner（凑桌算法）、card（SVG 方案卡）、render（终端渲染）、cli（plan/card/demo/fetch 子命令）、demo（合成数据） |
| 5. 测试 | 「如果需要管理python用uv」 | 用户要求用 uv 管理环境；改用 uv venv + uv pip install；编写 34 个 pytest 用例并全部跑通 |
| 6. 接真实数据 | 「我刚用我的麦当劳账号申请的 MCP Token放到.env里了」 | 用户自行申请 Token 放入 .env；WorkBuddy 解析裸 Token/.env、打通 MCP Streamable HTTP；实测发现并适配：query-nearby-stores 必填 searchType/beType、query-meals 必填 orderType、返回为「Markdown 说明+内嵌 JSON」需 raw_decode 提取、营养数据为文本表格、我的券为 Markdown 渲染、价格为元的字符串、SSL 抖动需退避重试 |
| 7. 迭代 | — | 增加商品券（用券价/买一送一）支持与券后价选品排序、营养名模糊匹配（大杯玉米杯↔玉米杯）、热量覆盖率提示 |
| 8. 提交 | 「你帮我做吧，我刚自己点了一个star来」 | 用户自行 star 仓库；WorkBuddy 创建公开仓库、提交代码、按官方格式提交报名 Issue #664，并整理本文件 |

## 关键设计决策（对话中形成）

1. **差异化选题**：榜单前 100 中省钱/卡路利/MBTI 类超过 30 个，「请客/团餐凑桌 + 分摊 + 分享卡」是空白场景，且能自然用上大量 MCP 工具。
2. **只读架构**：mcd-host 本体只调用只读 MCP 工具白名单，下单等写操作一律不碰，由用户在 MCP 客户端确认后自行完成——兼顾自动化与安全，也是 SKILL.md 的核心规则。
3. **凑桌算法可解释**：套餐优先（<¥20 的单人随心配不算正餐）→ 单点兜底（主食/饮料按人、小食每 2 人一份、甜品按场合每 3 人一份）→ 预算控制（核心 > 小食 > 甜品，超预算不加共享项）→ 一单一张券挑最省。
4. **券模型**：满减券 / 用券价商品券 / 买一送一券三类，选品时按券后有效价排序，最后精确计算。
5. **Agent 双入口**：终端 CLI（`mcd-host --json`）+ SKILL.md（WorkBuddy / Claude Code / Kiro），Skill 推荐 `--input` 一次给全 MCP 数据。

## 使用的 WorkBuddy 能力

- 文件读写与命令行执行（项目搭建、git/gh 操作、测试运行）
- 联网检索（比赛规则、MCP 工具入参规范）
- 任务管理（6 项任务清单跟踪进度）
- 数据可视化（赛事时间线图）

## 真实性说明

- 本文件所述开发过程均发生在 WorkBuddy 会话中，可由仓库 git 历史（首次提交 2026-10-14）与报名 Issue #664 相互印证；
- MCP Token 由用户本人在 open.mcd.cn 申请并存放于本机 .env（已被 .gitignore 忽略，未进入仓库任何提交）；
- 仓库中的真实数据示例（README、assets/host-card-real.svg）为用户账户在麦当劳 MCP 上的实时查询结果。
