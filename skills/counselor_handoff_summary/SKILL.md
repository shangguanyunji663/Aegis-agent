---
name: counselor_handoff_summary
description: Staff-facing handoff summary template for counselor or administrator review.
---

# Counselor Handoff Summary

## Purpose

Prepare a concise staff-facing handoff summary for counselor or administrator review.

## Trigger Conditions

- High risk report.
- Medium risk case needing human follow-up.

## Inputs

- User message excerpt.
- Risk level and rationale.
- Memory summary and current session context.

## Output Contract

- Summarize the concern and risk signal.
- Include recommended follow-up actions.
- Keep only necessary safety information.

## Safety Constraints

- Summarize the student expression, observed risk level, rationale, and current session context.
- Include recommended follow-up actions for a counselor or administrator.
- Keep the excerpt bounded and avoid unnecessary personal data.

## Example

Staff summary pattern: "学生表达强烈绝望并出现高风险信号。建议确认当前位置、是否独处、身边支持者和后续转介安排。"
