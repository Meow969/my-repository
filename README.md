# Meow 的 AI 购物雷达 · Evidence edition

在线网站：https://meow969.github.io/my-repository/

## 每日自动更新

GitHub Actions `.github/workflows/daily-update.yml` 每天 **北京时间 11:00** 计划执行：发现 → 提取原文 → 分级筛选 → 更新来源绑定的产品思考与回声 → 校验 → 自动提交 → GitHub Pages 发布。GitHub 的调度可能延迟，不承诺整点完成。无需本机在线，也无需模型密钥。英文关键简介使用本地 OPUS-MT 翻译模型生成中文，模型首轮自动下载并缓存。`workflow_dispatch` 可立即手动执行；推送代码只测试和发布，不重复采集。

## 页面阅读顺序

沿用紫色渐变科技感与双Tab：**有事没事来看看 / 回声**。默认打开最新月份，月份时间线下直接展示当月总结和最多5篇推荐，再按日期倒序展示每天的资讯集锦。无首页介绍区或来源方法Tab；收藏、证据筛选与展开阅读仍保留；卡片按“中英文标题与关键词 / 核心信息 / AI导购产品洞察与深入思考”排列，分析默认展开。英文标题保留原文并同时显示中文译名，顶部提供明确的原文链接。

## 信息质量改进

- 32 个可配置直连源：官方发布、行业媒体、综合媒体、研究资料、观点分析；另有72组中英文发现查询。来源的**实际可用数量**见 `data/source_health.json`，不是把配置数当成成功数。
- RSS/Atom命名空间兼容，保留真正发布日期；sitemap的lastmod不当作发布时间，缺失/未来日期不制造今日新闻。
- 提取原文句子并保留出处；原文、摘要、仅标题历史线索分级。新收录不接受仅标题。完整度分数不是事实正确概率。
- URL/标题严格去重，不因“同平台＋同一天”或相同模板洞察删除不同事件。精选按发布域名和主题打散。
- 产品思考由原文短摘录驱动，不复用固定主题结论；来源证据等级、模型推演与待验证问题分别标明。官方材料与多篇转载不等于独立验证。
- 既有灵感保存在 `data/legacy_insights.json`，可从回声打开；迁移前文章也保留。浏览器笔记存储键未更改，支持导出笔记与收藏。
- 无新增时不编造趋势；全部来源故障时失败退出，不覆盖已发布数据。网站超过48小时未更新会显示提醒。

## 本地运行

```sh
python3 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
.venv/bin/python -m http.server 8788
```

打开 http://localhost:8788 。GitHub Pages不支持服务端笔记搜索，沿用原有站内匹配/外部搜索兜底。笔记只保存在当前浏览器，请定期导出。

## 手动更新与检查

```sh
.venv/bin/python scripts/evidence_pipeline.py --days 45 --limit 24 --max-google-queries 72
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/validate_data.py
node --check app.js
```

`--recheck` 重新核验全部文章；默认每天最多复核12条超过7天未检查的旧文章。`--dry-run` 不写文件。旧 `update_content.py` 命令兼容并转到新流程。

## 数据

- `articles.json` — 信息、原文摘录、中文简介（`summaryZh`）、译文对应原文哈希、证据级别、分类和核验时间。
- `insights.json` — 多材料研究与单篇闪念，默认精简展示，依据可展开。
- `research_queue.json` — 原文变化或模型暂不可用、仅能提供待验证问题的记录。
- `daily_digest.json` — 近14天多来源原文精选与当次新增数。
- `monthly_reports.json` — 每月主题总结、推荐文章和总结对应资料；随每日采集更新。
- `source_health.json` — 每个来源本次结果、候选数和错误状态。
- `meta.json` — 最近成功刷新时间、质量统计、来源健康度。
- `legacy_*.json` — 升级前存档，用于追溯与回滚。

限制：付费墙、反爬和动态网页可能使正文不可读；这类内容降为观察线索或不收录。重复判断不是全网语义事件聚类，来源域名不同也不保证独立采访。

## 历史回刷与中文简介

`backfill_evidence.py` 按月、按国内外分配候选预算，避免只搜出最新月份；支持2025年9月至今的历史查询。先缓存候选与核验结果，生成暂存文件，不直接覆盖线上数据。`radar_queries.json` 集中维护每日主题，可持续增补案例、竞品、研究和咨询机构。

中文简介为原文短摘录的中文翻译，不改写原文标题或冒充新的事实。模型运行在CPU，不上传原文到翻译服务；缓存命中则不重新生成。模型许可为 CC BY 4.0，详见 `TRANSLATION_LICENSE.md`。发布校验会拦截缺少中文简介或原文哈希不匹配的数据。单条新资讯翻译失败则暂不收录，其余资讯继续更新；模型下载等系统故障会中止发布，保留上一版。

历史回刷仍经过原文核验、主题筛选与去重；旧闻按原始发布日期归档，而不是按回刷日期伪装成今日新闻。

## 资讯产品思考与回声研究

- 每条资讯保留中文摘要及产品思考。`data/article_thinking.json` 按原文标题、地址、摘录与证据级别绑定生成结果，`evidenceIndex` 与短引用必须实际存在于输入。
- 正文区只留一个具体判断、一项取舍和一个验证办法；不再复用固定导购模板，也不以“已人工复核”描述模型输出。只有标题或摘要时必须按条件假设阅读。
- “回声”分为多材料研究与单篇闪念。多材料卡由 `echo_topics.json` 定义的问题出发，至少比较2篇可追溯材料，呈现判断、分歧、行动与证据边界；每篇来源变化后，该版本卡片暂停展示。单篇闪念按来源打散。
- `source_thinking.py` 支持配置兼容 Responses / Chat Completions 的推理接口。环境变量：`RADAR_LLM_ENDPOINT`、`RADAR_LLM_MODEL`、可选 `RADAR_LLM_API_KEY`。密钥只留在服务端，不进入网页或仓库。
- GitHub Actions 可以读取同名仓库 Variables（地址/模型）与 Secret（API Key）。未配置远端模型时仍自动采集、翻译、发布资讯，已缓存有效分析继续保留；新材料提供明确标为“待验证问题”的来源思考，不伪造模型生成或人工审核状态。深入模型分析可通过本地配置的推理端补全后发布。
- 本次已有资料已逐条重新生成；缓存只随源文变化失效，不因日期变化反复花费调用。`reviewed_research.json` 中历史人工核对的短引文仍可作为额外证据，不能拿来替换另一条新闻的结论。
- 旧版回声及用户附注对应ID保存在历史入口。笔记、收藏与原有浏览器存储键保持不变。

更新思考：

```sh
python scripts/source_thinking.py --workers 2 --batch-size 8
python scripts/echo_synthesis.py
```

部署前运行单元测试、`scripts/validate_data.py` 与浏览器烟测。检查每条分析的来源哈希、引文归属、字段长度、重复正文，以及每张跨材料卡是否包含至少2篇实际出处。
