# 本地开发流程

本项目多数时候由少量协作者推进，但仍按稳定分支和开发分支区分，避免交付包、文档和代码状态混乱。

## 1. 分支策略

- `main`：稳定分支，只放可运行、可交付的版本。
- `dev`：日常开发分支，所有功能、文档、实验改动先进入这里。
- `feature/*`：较大功能或高风险改动可单独开分支，例如：
  - `feature/schedule-view`
  - `feature/group-qualification`
  - `feature/model-review`
- `fix/*`：明确缺陷修复可单独开分支，例如：
  - `fix/llm-ssl`
  - `fix/report-rendering`

合并方向：

```text
feature/* -> dev
fix/*     -> dev
dev       -> main
```

## 2. 日常开发流程

1. 在 `dev` 分支讨论需求和边界。
2. 给出推荐方案和取舍。
3. 更新 `specs/`、`README.md` 或 `PROJECT_RULES.md`。
4. 实现代码或页面改动。
5. 运行必要检查。
6. 提交到 `dev`。
7. 阶段性稳定后，再从 `dev` 合并到 `main`。

## 3. 什么时候合并到 main

只有在阶段节点合并到 `main`：

- 一个用户可感知功能完成。
- 一组规格或文档稳定。
- 修复了影响使用的关键问题。
- 准备重新打包交付 zip。
- 本地服务能启动，基础流程跑通。

不要把半成品实验直接合并到 `main`。

## 4. main 合并前检查清单

合并到 `main` 前至少运行：

```bash
python3 -m py_compile app.py worldcup_ai_repro.py visualize_predictions.py
node --check web/app.js
git status --short
```

如果涉及网页体验，还应手动检查：

- 首页能打开。
- 预测能运行。
- 模拟次数配置生效。
- 比分能保存。
- 报告能生成。
- LLM 未配置时基础功能可用。
- LLM 配置失败时有清晰提示。
- 交付包不包含 `app_data/`、`.git/`、缓存文件或本机临时文件。

## 5. 提交规范

- 一个 commit 尽量表达一个主题。
- 文档和代码可以一起提交，但应服务同一个变化。
- 不提交运行时数据、缓存、生成报告、API Key 或本机绝对路径。
- 提交信息使用简短英文动词短句，例如：
  - `Improve LLM SSL verification handling`
  - `Display team names in Chinese`
  - `Apply AI factors to predictions`
  - `Document roadmap and project workflow`

## 6. 文档同步规则

用户可感知的变化需要同步文档：

- 项目定位变化：更新 `README.md` 和 `specs/PRODUCT_SPEC.md`。
- 页面流程变化：更新 `specs/UX_SPEC.md`。
- LLM 参与方式变化：更新 `specs/AI_SPEC.md`。
- 数据结构变化：更新 `specs/DATA_SPEC.md`。
- 开发阶段变化：更新 `specs/IMPLEMENTATION_PLAN.md`。
- 尚未实现的新需求：记录到 `specs/TODO.md`。

## 7. 打包交付规则

交付包应从稳定状态生成，优先在 `main` 节点打包。

推荐命令：

```bash
zip -r ../../outputs/worldcup_ai_repro.zip . \
  -x '__pycache__/*' 'app_data/*' '.git/*' '.git' '.DS_Store'
```

打包后确认：

- 包含 `data/results.csv` 和 `data/results_source.md`。
- 不包含用户运行数据 `app_data/`。
- 不包含 Git 仓库内部目录。
- 不包含 API Key 或本机临时文件。

## 8. 版本记录

后续可新增 `CHANGELOG.md`。每次 `dev -> main` 时记录：

- 新增功能。
- 修复问题。
- 数据源变化。
- 模型参数变化。
- 已知限制。
