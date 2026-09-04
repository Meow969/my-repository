# 公开访问部署方式

## 推荐：Vercel（支持“记笔记”的联网搜索）

1. 新建一个 GitHub 仓库，把 `/Users/yangmengyao.20/my_project` 推到仓库。
2. 登录 Vercel，选择 `Add New → Project`，导入该仓库。
3. Root Directory 选择 `ai-shopping-radar`。
4. Vercel 会读取项目内 `vercel.json`。
5. 部署完成后会得到公开链接，所有设备都能访问。

## Netlify（支持“记笔记”的联网搜索）

1. 登录 Netlify，选择 `Add new site → Import from Git`。
2. 选择仓库后，Build settings 使用：
   - Base directory: `ai-shopping-radar`
   - Build command: `python3 scripts/update_content.py --days 30 --limit 8`
   - Publish directory: `.`
3. 部署完成后会得到公开链接。

## GitHub Pages（静态兜底）

GitHub Pages 可以公开访问静态页面，但不支持站内服务端联网搜索函数。使用 GitHub Pages 时，“记笔记”会保留站内匹配和外部搜索链接兜底；如果要自动返回至少 3 条全网结果，建议用 Vercel 或 Netlify。

已配置 GitHub Pages 工作流：`/Users/yangmengyao.20/my_project/.github/workflows/ai-shopping-radar-pages.yml`，每天北京时间 11:00 自动更新并发布。

## 注意

当前我无法直接替你生成永久公网 URL，因为这需要你的 GitHub、Vercel 或 Netlify 账号授权。配置已经完成，只差把目录推到你的托管账号。
