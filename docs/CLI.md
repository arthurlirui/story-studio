# Story Studio CLI 文档

`ss` 是 Story Studio 的统一命令行接口，基于 Typer + Rich 构建。

## 安装

```bash
pip install -e ".[cli]"
```

安装后 `ss` 命令可用。若 Scripts 目录不在 PATH，可用 `python -m cli.main` 替代。

## 全局选项

全局选项须放在子命令前：

```bash
ss [全局选项] <子命令> [子命令选项]
```

| 选项 | 说明 |
|------|------|
| `-v, --verbose` | 详细输出（`-v` INFO, `-vv` DEBUG, `-vvv` 全量） |
| `--config <path>` | 指定 settings.yaml 路径（默认 config/settings.yaml） |
| `-n, --no-interaction` | 非交互模式（CI 友好，不弹确认） |

## 命令树

```
ss
├── run                         运行生成管线
│   ├── pipeline <task>         长篇系列管线（替代 run_all.py）
│   ├── short <task>            短篇管线（替代 run_short.py）
│   ├── stage <phase>           单 phase 执行
│   └── polish <chapter>        单章去AI化
├── submit <brief>              提交后台 Job
├── status                      系统/项目状态
├── jobs                        管理后台 Job
│   ├── list                    列出 Job
│   ├── show <id>               查看 Job 详情
│   ├── cancel <id>             取消 Job
│   └── retry <id>              重跑失败 Job
├── list                        列出内容
│   ├── novels                  列出小说
│   ├── series                  列出系列
│   └── chapters <novel>        列出章节
├── export                      导出成品
│   ├── final <novel>           合并章节为成品
│   └── covers <novel>          导出封面 brief
├── config                      配置管理
│   ├── get <key>               读取配置值
│   ├── set <key> <value>       写入配置值
│   ├── show                    脱敏打印配置
│   └── path                    打印配置文件路径
├── agents                      智能体团队
│   ├── list                    列出智能体（树形图）
│   └── inspect <name>          查看智能体详情
└── repl                        交互式 REPL
```

## 常用示例

```bash
# 查看系统状态
ss status
ss status --format json          # 机器可读输出

# 提交后台生成任务
ss submit "一个关于急诊室医生的故事" --name 急诊室 --chapters 20 --mode batch

# 查看 Job
ss jobs list
ss jobs list --status running --format json
ss jobs show 1709xxxx_a1b2c3d4

# 运行长篇管线（替代 python run_all.py）
ss run pipeline 轮回怪谈 --variant 01 --stage deai --dry-run

# 运行短篇
ss run short modern_romance

# 单章去AI化
ss run polish 5 --prompt-version v4

# 列出系列与章节
ss list series
ss list chapters "series/千行百业/variants/03_雷雨请绕飞"

# 导出成品
ss export final "series/千行百业/variants/03_雷雨请绕飞" --format txt --out final.txt

# 配置管理
ss config show                   # 脱敏打印（密钥显示 sk-d****）
ss config get main_model
ss config set batch_size 5
ss config set research_enabled true

# 智能体
ss agents list                   # 按 main/light tier 分组树形图
ss agents inspect showrunner     # 查看 system_prompt

# 交互式 REPL（迁移自 main.py）
ss repl
# /new <需求>  /next  /write [章号]  /plan  /run-all  /resume  ...
```

## 向后兼容

`python main.py` 仍可用，旧 flag 自动转译：

```bash
python main.py                  # = ss repl
python main.py --status         # = ss status
python main.py --submit "需求"  # = ss submit "需求"
python main.py --jobs           # = ss jobs list
```

## 输出格式

- **table**（默认）：Rich 格式化表格/面板/树，带颜色和图标
- **json**：`--format json` 输出纯 JSON，供脚本/CI 消费

## 设计要点

- **懒加载**：子命令模块仅在调用时 import orchestrator（93KB），`ss --help` 秒级响应
- **Rich 集成**：Typer 内置 Rich，异常 traceback 自动格式化（`pretty_exceptions_show_locals=False` 防止密钥泄露）
- **脱敏**：`config show` / `config get llm_api_key` 自动脱敏，拒绝通过 `config set` 写入敏感字段
