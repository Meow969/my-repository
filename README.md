# AI购物雷达

一个持续更新的网站，用于沉淀过去一年及每日新增的国内外 AI C 端产品、购物、导购、购物智能体和 Agentic Commerce 高价值信息。

## 本地查看

```bash
cd /Users/yangmengyao.20/my_project/ai-shopping-radar
./scripts/serve.sh
```

打开：`http://localhost:8787`

推荐用上面的本地服务；它同时支持“记笔记”的联网搜索接口。

## 数据结构

- `data/articles.json`：每日精选信息流。
- `data/insights.json`：跨文章沉淀后的 AI 导购产品灵感集。
- `data/monthly_reports.json`：按月沉淀的极简月报和当月 Top 信息。
- `data/meta.json`：更新时间、站点说明、筛选规则。

每条信息包含：标题、链接、关键词标签、核心观点、深入洞察、价值分、关联灵感。

页面能力：

- 按月时间线切换过去一年历史信息。
- 每月自动生成/维护 Top 关注信息入口。
- 灵感集词云只展示产品洞察关键词，不展示泛标签。

## 手动更新

```bash
cd /Users/yangmengyao.20/my_project/ai-shopping-radar
python3 scripts/update_content.py --days 30 --limit 8
```

脚本会搜索近 30 天候选，按相关性、来源质量、信息密度和产品启发度打分，只追加高价值内容。

## 每天 11 点自动更新（本机）

```bash
cd /Users/yangmengyao.20/my_project/ai-shopping-radar
./scripts/install_macos_schedule.sh
```

安装后会创建 macOS LaunchAgent：`~/Library/LaunchAgents/com.ai-shopping-radar.update.plist`。

日志位置：

- `logs/update.out.log`
- `logs/update.err.log`

## 公开部署与定时更新

推荐部署到 Vercel 或 Netlify，这样“记笔记”的联网搜索可以正常返回结果。GitHub Pages 可做静态兜底。仓库根目录的 `.github/workflows/ai-shopping-radar-pages.yml` 会在每天北京时间 11:00 自动更新并发布到 GitHub Pages。

公开访问部署说明见：`DEPLOY.md`。

## 筛选原则

优先收录：

- AI 购物、AI 导购、购物智能体、Agentic Commerce。
- 国内外 C 端 AI 产品的新功能、新入口、新闭环。
- 对产品设计、商业模式、商家接入、交易履约有启发的信息。

过滤：

- 纯融资新闻。
- 泛 AI 营销软文。
- 重复通稿。
- 没有产品洞察的工具清单。
