# GITEA-AI-CODEVIEW

本项目是 hack Github Copilot 的 api,获取代码提交的 `diff` 信息，提交给 Copilot 审查，然后创建到 Gitea issue 或 PR 评论上。

## 功能特性

- 支持代码提交（commit）审查
- 支持 Pull Request 审查
- 自动评分和问题分析
- 支持自动批准符合标准的 PR
- 支持详细的代码审查评论
- 支持跳过代码审查（提交信息包含 `[skip codereview]`）
- 支持多种 AI 服务（Github Copilot 和 DeepSeek）
- 支持自动合并通过审查的 PR
- 支持 Webhook 通知

## 环境变量

| 环境变量名           | 描述                       | 默认值                                      |
| -------------------- | -------------------------- | ------------------------------------------- |
| GITEA_TOKEN          | 用于访问 Gitea API 的令牌  | 无                                          |
| GITEA_HOST           | Gitea 服务器的主机地址     | 无                                          |
| COPILOT_TOKEN        | 用于访问 Copilot 的密钥    | 无                                          |
| DEEPSEEK_KEY         | 用于访问 DeepSeek 的密钥   | 无                                          |
| DEEPSEEK_PASS_SCORE  | DeepSeek代码审查通过分数   | 70                                          |
| IGNORED_FILE_SUFFIX  | 忽略的文件后缀             | 无                                          |
| WEBHOOK_URL          | web hook url               | 无                                          |
| WEBHOOK_HEADER_NAME  | web hook 请求头字段名      | 无                                          |
| WEBHOOK_HEADER_VALUE | web hook 请求头字段内容    | 无                                          |
| WEBHOOK_REQUEST_BODY | web hook 请求体 json       | 占位符为 content 消息正文，mention 提到的人 |

## 开发

```shell
copy .env.example .env # 创建配置文件 获取 Gitea 仓库的 `access_token`， `host` 以及 Copilot `COPILOT_TOKEN` 配置到 `.env` 文件中。
python -m venv .venv && ./venv/Scripts/activate # 创建虚拟环境并激活
pip install -r requirements.txt || poetry install # 安装依赖，如果安装了 poetry 建议使用 poetry 命令
python main.py # 运行
访问 http://127.0.0.1:3008/docs
```

## Webhook 配置

### Commit 审查
- 端点: `http://{server_host}:{server_port}/codereview`

### Pull Request 审查
- 端点: `http://{server_host}:{server_port}/pr_review`
- 触发事件: Pull Request

![](./doc/hook.jpg)

## AI 服务配置

系统支持两种 AI 服务：
1. Github Copilot：设置 `COPILOT_TOKEN` 环境变量
2. DeepSeek：设置 `DEEPSEEK_KEY` 环境变量

系统会按以下优先级选择 AI 服务：
1. 如果配置了 `COPILOT_TOKEN`，使用 Copilot
2. 如果配置了 `DEEPSEEK_KEY`，使用 DeepSeek
3. 如果都未配置，系统将报错

## 代码审查结果

代码审查会生成详细的评论，包含以下信息：
- 总体评分
- 审查状态（通过/需要修改）
- 各个提交的详细评审结果：
  - 提交信息
  - 评分
  - 状态
  - 具体问题（如果有）：
    - 问题类别（代码质量/性能优化/安全性/最佳实践）
    - 严重程度
    - 问题描述
    - 改进建议
    - 代码示例（如果适用）

如果所有提交的代码质量都达到设定的通过分数：
- 系统会自动批准 PR
- 尝试自动合并 PR
- 发送 Webhook 通知（如果配置了 webhook）

## 提示

- 如果提交信息包含 `[skip codereview]` 将跳过代码审查
- `WEBHOOK_REQUEST_BODY` 最外层括号要转义，`{...}` -> `{{...}}`
- 系统会自动过滤 `.sql` 文件的审查
- PR 评论使用 Markdown 格式，支持代码块和引用样式
