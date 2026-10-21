---
name: test-skill
description: >-
  测试技能，用于验证路由与门禁链路。触发词：测试技能、test skill。
license: MIT
metadata:
  author: Skrepy0
  version: "0.1.0"
  required_fields:
    - topic
  output: markdown
  sections:
    - 概述
    - 正文
  gates:
    cliche_check: 1.0
---

# 测试技能

## 阶段一：信息采集

检查 `topic` 字段。缺失则追问：“你想测试什么主题？”

## 阶段二：结构化生成

按 `sections` 逐章生成，每章 100–300 字。

## 阶段三：自检清单

- [ ] 章节齐全
- [ ] 无“名列前茅”“填补空白”等套话