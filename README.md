# WeRead to Notion Pro

将微信读书的书籍、划线、个人笔记、阅读进度和每日阅读汇总同步到
Notion 的个人工具。

## 当前状态

当前版本包含：

- 微信读书风格的本地同步状态 UI 原型
- Books、Annotations、Reading Days 三库数据模型
- 源 ID 去重、增量同步和删除标记设计
- 本地配置模板
- 同步规约与 Notion 字段契约

真实微信读书和 Notion API 同步仍在实现中。

## 启动本地 UI

```bash
python3 server.py
```

然后打开 <http://127.0.0.1:8765>。

## 本地配置

复制配置模板：

```bash
cp config/local.example.toml config/local.toml
```

`config/local.toml` 已被 Git 忽略，不应提交 API Key 或 Notion Token。

## 设计文档

- `docs/adr/0001-personal-github-actions-sync.md`
- `docs/notion-schema.md`
- `specs/workflows/wread2notion-sync.spec.md`
