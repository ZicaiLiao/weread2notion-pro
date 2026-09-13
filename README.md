# WeRead to Notion Pro

将微信读书的书籍、划线、个人笔记、阅读进度和每日阅读汇总同步到
Notion 的个人工具。

## 当前状态

当前版本以 CLI 同步命令为运行入口，包含：

- 微信读书 Agent Gateway 数据读取
- Books、Annotations、Reading Days 三库自动创建与幂等 upsert
- Source ID 去重、全量删除标记和增量同步
- 本地配置模板与 GitHub Actions 工作流

`static/` 保留为已经废弃的 UI 原型，仅作为数据库字段和信息架构的
视觉参考，不再维护，也不会参与同步流程。

## 本地同步

```bash
cp config/local.example.toml config/local.toml
# 填写 weread_api_key、notion_token、notion_parent_page_id
python3 -m wread2notion --config config/local.toml --mode full --json
```

命令会自动开始同步，不需要点击确认。配置文件已被 Git 忽略，不能提交
API Key 或 Notion Token。

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
- `specs/weread-to-notion-v1.spec.md`
