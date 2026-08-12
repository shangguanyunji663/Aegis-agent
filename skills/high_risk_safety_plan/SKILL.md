---
name: high_risk_safety_plan
description: Safety-first guidance when a student expresses self-harm or immediate danger.
---

# High Risk Safety Plan

## Purpose

Prioritize immediate safety when the student expresses self-harm or imminent danger.

## Trigger Conditions

- High risk from RiskGuardianAgent.
- Mentions 自杀, 轻生, 结束生命, cannot stay safe, or similar expressions.

## Inputs

- Current user message.
- Risk rationale.
- Session ID for backend report creation only; never expose it to the student.

## Output Contract

- Ask the student to reduce immediate danger.
- Encourage not staying alone.
- Encourage contacting trusted people, campus counseling, or local emergency support.

## Safety Constraints

- Prioritize immediate physical safety.
- Encourage the student not to stay alone.
- Encourage contacting a trusted person, campus counseling center, or local emergency service.
- Do not describe self-harm methods, lethal means, or operational details.

## Example

User: "我不想活了。"
Reply pattern: "我很在意这个危险信号。请先不要一个人待着，尽快联系身边可信任的人陪你一起联系学校心理中心或当地紧急服务。"
