# 中文简介翻译模型与引用

英文原文短摘录在本机 / GitHub Actions 上使用 OPUS-MT 英中模型生成中文，重点案例另有基于原文哈希绑定的人工校订。无需翻译 API 或密钥。译文仅供阅读，原文是事实核对依据；模型可能误译术语和专有名词。

- 模型作者：Jörg Tiedemann、Santhosh Thottingal。
- 引用：OPUS-MT — Building open translation services for the World，EAMT 2020，Lisbon, Portugal。
- 项目：https://github.com/Helsinki-NLP/Opus-MT
- 使用 Argos 打包的 English–Chinese 1.9 模型：https://argos-net.com/v1/translate-en_zh-1_9.argosmodel
- 原模型许可：**CC BY 4.0**，https://creativecommons.org/licenses/by/4.0/
- 打包文件 SHA-256：`433e7c4f034d87fbe2353161e05f18646d7999452f801a4e1f0378522b9850ab`。
- CTranslate2 / SentencePiece 运行库遵循各自许可；模型文件不提交到仓库或网站发布物。
- 本项目额外规范了电商术语，保留原文标题；`editorial_summaries.json` 是人工校订的中文简介，只有原文哈希匹配时才使用。

中文简介与短原文摘录分别保存。原文摘录改变后才重新翻译；翻译失败或未生成中文时，发布校验失败，保留上一版站点。
