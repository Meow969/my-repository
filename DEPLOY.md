# 发布与恢复

仓库：`Meow969/my-repository`，线上：https://meow969.github.io/my-repository/

1. 在独立分支修改并运行README中的测试和数据校验。
2. 推送经过验证的提交到 `main`。GitHub Actions测试后发布到GitHub Pages。
3. 在Actions中确认 `Update and Publish AI Shopping Radar` 成功；检查线上 `data/meta.json` 与新资源版本。
4. 每日计划与手动触发会先采集再发布；推送触发只发布已核验的数据。

发布物仅包含静态页面、样式、脚本和公开数据，不包含开发脚本、日志、依赖或凭据。失败不会替换上一次成功的Pages站点。部分来源不可用会记录在 data/source_health.json；全部不可用直接让任务失败。

回滚：对有问题的发布提交执行 `git revert <commit>` 并推送main，不要强推。必要时在GitHub Actions中临时禁用工作流，再修复/恢复。旧版内容已归档，笔记位于用户浏览器，不属于发布数据。

定时任务为UTC 03:00（北京时间11:00）；GitHub有排队延迟。超过48小时未更新时网站提示检查任务。建议保持GitHub Actions失败通知开启。
