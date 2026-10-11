# 改进记录索引（docs/records/）

> 本目录集中存放**历轮改进记录**：做了什么、为什么、变更清单与实测数据。
> 面向读者的学习文档（[逐文件学习指南](../../Aegis项目逐文件学习指南.md) · [前端学习指南](../frontend-learning-guide.md)）只保留定稿内容，不含过程性叙述。
> 路线图类文档在 [`docs/roadmap/`](../roadmap/)；训练侧证据在 [`docs/training/`](../training/)。

## 一、按轮次（第一 ~ 第二十一轮）

| 轮次 | 主题 | 文档 |
| --- | --- | --- |
| 第一轮 | 模块化重构 | [REFACTORING.md](REFACTORING.md) |
| 第二轮 | 响应提速与真流式 | [OPTIMIZATION.md](OPTIMIZATION.md) |
| 第三轮 | 注册登录与 MySQL 持久化 | [AUTH-MYSQL.md](AUTH-MYSQL.md) |
| 第四轮 | LangGraph 编排与全栈激活 | [LANGGRAPH-DOCKER.md](LANGGRAPH-DOCKER.md) |
| 第五轮 | 深度增强（风险双通道 / FC / 评测 / Judge / Checkpoint） | [DEEP-ENHANCEMENTS.md](DEEP-ENHANCEMENTS.md) |
| 第六轮 | 回复真人化 | [LLM-RESPONSE-HUMANIZATION.md](LLM-RESPONSE-HUMANIZATION.md) |
| 第七轮 | 记忆系统增强 | [MEMORY-ENHANCEMENT.md](MEMORY-ENHANCEMENT.md) |
| 第八轮 | 对抗型对话测试 | [CONFRONTATIONAL-DIALOGUE-TESTING.md](CONFRONTATIONAL-DIALOGUE-TESTING.md) |
| 第九轮 | 项目文档整合与规范化 | [ROUND-9-CONSOLIDATION.md](ROUND-9-CONSOLIDATION.md) |
| 第十轮 | 代表性语料双层拆分 | [CORPUS-LAYER-SPLIT.md](CORPUS-LAYER-SPLIT.md) |
| 第十一轮 | 风险 LLM 通道双路径验证 | [ROUND-11-RISK-LLM-DUAL-CHANNEL.md](ROUND-11-RISK-LLM-DUAL-CHANNEL.md) |
| 第十二轮 | RAG 增强与性能基准 | [ROUND-12-RAG-ENHANCEMENT-BENCHMARK.md](ROUND-12-RAG-ENHANCEMENT-BENCHMARK.md) |
| 第十三轮 | 记忆分层与 Skill 自动蒸馏 | [ROUND-13-MEMORY-SKILL-DISTILLATION.md](ROUND-13-MEMORY-SKILL-DISTILLATION.md) |
| 第十五轮 | 前端疗愈主题升级 | [ROUND-15-FRONTEND-CALM-THEME.md](ROUND-15-FRONTEND-CALM-THEME.md) |
| 第十六轮 | 咨询工作台教师手册 | [ROUND-16-ADMIN-TEACHER-GUIDE.md](ROUND-16-ADMIN-TEACHER-GUIDE.md) |
| 第十七轮 | 前端整体改造 | [ROUND-17-FRONTEND-OVERHAUL.md](ROUND-17-FRONTEND-OVERHAUL.md) |
| 第十八轮 | 前端多主题切换 | [ROUND-18-THEME-SWITCHER.md](ROUND-18-THEME-SWITCHER.md) |
| 第十九轮 | RAG 语义重排引擎（Cross-Encoder）与真 MiniLM 实测 | [ROUND-19-RAG-SEMANTIC-RERANK.md](ROUND-19-RAG-SEMANTIC-RERANK.md) |
| 第二十轮 | 前端三概念主题系统（Vite + React + TS） | [ROUND-20-FRONTEND-SCENE-DRIVEN.md](ROUND-20-FRONTEND-SCENE-DRIVEN.md) |
| 第二十一轮 | RAG 本地化升级（中文嵌入 / CE 融合精排 / 570 块扩库 / 生产 bug 修复） | [ROUND-21-RAG-LOCAL-UPGRADE.md](ROUND-21-RAG-LOCAL-UPGRADE.md) |

## 二、专题档案

| 文档 | 内容 |
| --- | --- |
| [GUIDE-REVIEW-ARCHIVE.md](GUIDE-REVIEW-ARCHIVE.md) | 学习指南四轮审阅 + 双目标适配性评估（2026-09）的结论、问题清单与修复状态 |
| [GUIDE-REVISIONS.md](GUIDE-REVISIONS.md) | 学习指南修订台账：每次改了什么、为什么、仍在执行的建议 |

## 三、命名说明

- 第一 ~ 八轮以**主题名**命名（早期无轮次编号约定）；第九轮起采用 `ROUND-N` 编号命名。
- 第十四轮（QLoRA 安全集成）记录在仓库外的训练仓，见 `docs/training/`。