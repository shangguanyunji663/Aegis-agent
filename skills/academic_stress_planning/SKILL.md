---
name: academic_stress_planning
description: Planning support for exam, thesis, GPA, and academic workload stress.
---

# Academic Stress Planning

## Purpose

Help students turn academic pressure into manageable next actions.

## Trigger Conditions

- User mentions exams, GPA, thesis, homework, coursework, deadlines, or study pressure.

## Inputs

- Current user message.
- Memory summary about prior academic stress when available.
- Relevant knowledge snippets.

## Output Contract

- Name the academic pressure clearly.
- Separate controllable actions from uncertain outcomes.
- Offer one small next task.

## Safety Constraints

- Help split the pressure into a next small task.
- Separate controllable actions from uncertain outcomes.
- Encourage contacting teachers, classmates, or counselors when workload becomes unmanageable.

## Example

User: "考试压力一直在。"
Reply pattern: "我们先不解决全部考试，只选今天最小的一步，比如整理一个错题主题或预约一次答疑。"
