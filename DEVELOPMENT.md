# 本地开发流程

本项目多数时候由少量协作者推进，但仍按稳定分支和开发分支区分，避免交付包、文档和代码状态混乱。

## 1. 分支策略

- `main`：稳定分支，只放可运行、可交付的版本。
- `dev`：日常集成分支，所有功能、文档、实验改动先进入这里，并保留完整开发提交历史。
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

发布节奏：

```text
feature/* --merge/squash--> dev --merge --no-ff--> main --tag--> vX.Y.Z
```

`main` 和 `dev` 都是长期分支。除非明确修复历史错误，不应通过 `reset --hard`、`rebase` 或强推改写这两个分支的公开历史。

## 2. 日常开发流程

1. 在 `dev` 分支讨论需求和边界。
2. 给出推荐方案和取舍。
3. 更新 `specs/`、`README.md` 或 `PROJECT_RULES.md`。
4. 实现代码或页面改动。
5. 运行必要检查。
6. 提交到 `dev`。
7. 阶段性稳定后，再从 `dev` 合并到 `main`。

## 3. 合并和 rebase 规则

### feature/fix 分支同步 dev

短生命周期、个人使用的 `feature/*` 或 `fix/*` 分支，可以用 `rebase` 同步最新 `dev`：

```bash
git switch feature/model-review
git fetch origin
git rebase dev
```

适用场景：

- 功能分支只由自己使用，尚未被他人基于它继续开发。
- 希望把功能提交重新接到最新 `dev` 后面，让历史保持线性。
- 合并前想提前解决和 `dev` 的冲突。

避免场景：

- 分支已经推送并被他人使用。
- 分支是 `main`、`dev`、`release/*` 等长期公共分支。

原因：`rebase` 会改写当前分支提交哈希，不适合改写长期公共分支历史。

### feature/fix 合入 dev

普通功能完成后，优先用真实合并保留功能边界：

```bash
git switch dev
git merge --no-ff feature/model-review
```

如果功能分支上只有大量临时提交、调试提交或反复修补提交，也可以 squash 后合入 `dev`：

```bash
git switch dev
git merge --squash feature/model-review
git commit -m "Add model review diagnostics"
```

选择建议：

- 用 `--no-ff`：功能较完整，提交历史有保留价值。
- 用 `--squash`：分支提交过程很乱，只希望保留最终改动。

### dev 发布到 main

`dev` 合入 `main` 时，默认使用 `--no-ff`，不使用 `--squash`：

```bash
git switch main
git merge --no-ff dev
git tag v0.2.2
```

原因：

- 保留 `dev` 上的完整开发提交历史。
- `main` 上会出现一个明确的发布合并提交。
- Git 能识别 `dev` 已经被合并过，后续不会重复合并旧改动。
- 避免 `dev --squash--> main` 后再对齐分支导致开发历史丢失。

`--squash` 可以用于短期功能分支，不建议用于长期 `dev -> main` 发布合并。

### main 与 dev 的关系

发布后通常不需要把 `dev` reset 到 `main`。`dev` 可以继续保留自己的开发历史并向前推进。

如果 `main` 上出现了只属于发布线的变更，例如版本文档、发布说明或紧急修复，应再合回 `dev`：

```bash
git switch dev
git merge --no-ff main
```

## 4. 什么时候合并到 main

只有在阶段节点合并到 `main`：

- 一个用户可感知功能完成。
- 一组规格或文档稳定。
- 修复了影响使用的关键问题。
- 准备重新打包交付 zip。
- 本地服务能启动，基础流程跑通。

不要把半成品实验直接合并到 `main`。

## 5. main 合并前检查清单

合并到 `main` 前至少运行：

```bash
python3 -m py_compile app.py app_config.py storage.py services/*.py worldcup_simulator.py visualize_predictions.py
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

## 6. 发布流程

当 `dev` 准备发布为新版本时：

```bash
git switch main
git pull --ff-only
git merge --no-ff dev
git tag v0.2.2
git push origin main
git push origin v0.2.2
```

如果远端 `dev` 也需要同步：

```bash
git switch dev
git push origin dev
```

发布后不要为了“对齐”而重置 `dev`。只有在明确要丢弃 `dev` 的开发历史，并且已经做好备份时，才考虑重置分支。

## 7. 提交规范

- 一个 commit 尽量表达一个主题。
- 文档和代码可以一起提交，但应服务同一个变化。
- 不提交运行时数据、缓存、生成报告、API Key 或本机绝对路径。
- 提交信息使用简短英文动词短句，例如：
  - `Improve LLM SSL verification handling`
  - `Display team names in Chinese`
  - `Apply AI factors to predictions`
  - `Document roadmap and project workflow`

## 8. 文档同步规则

用户可感知的变化需要同步文档：

- 项目定位变化：更新 `README.md` 和 `specs/PRODUCT_SPEC.md`。
- 页面流程变化：更新 `specs/UX_SPEC.md`。
- LLM 参与方式变化：更新 `specs/AI_SPEC.md`。
- 数据结构变化：更新 `specs/DATA_SPEC.md`。
- 开发阶段变化：更新 `specs/IMPLEMENTATION_PLAN.md`。
- 尚未实现的新需求：记录到 `specs/TODO.md`。

## 9. 打包交付规则

交付包应从稳定状态生成，优先在 `main` 节点打包。

推荐命令：

```bash
zip -r ../../outputs/worldcup_simulator.zip . \
  -x '__pycache__/*' 'app_data/*' '.git/*' '.git' '.DS_Store'
```

打包后确认：

- 包含 `data/results.csv` 和 `data/results_source.md`。
- 不包含用户运行数据 `app_data/`。
- 不包含 Git 仓库内部目录。
- 不包含 API Key 或本机临时文件。

## 10. 版本记录

后续可新增 `CHANGELOG.md`。每次 `dev -> main` 时记录：

- 新增功能。
- 修复问题。
- 数据源变化。
- 模型参数变化。
- 已知限制。
