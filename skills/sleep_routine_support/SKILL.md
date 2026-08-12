---
name: sleep_routine_support
description: Sleep routine support for insomnia and disrupted rest.
---

# Sleep Routine Support

## Purpose

Support sleep and routine problems related to stress or rumination.

## Trigger Conditions

- User mentions 睡不着, 失眠, 睡眠, 熬夜, or repeated late-night rumination.

## Inputs

- Current user message.
- Knowledge snippets about sleep.
- Memory summary when sleep problems repeat.

## Output Contract

- Avoid demanding immediate sleep.
- Offer one action for tonight.
- Recommend help if sleep problems persist or combine with low mood/risk.

## Safety Constraints

- Start with one small action the student can try tonight.
- Suggest reducing late stimulation, writing down worries, and setting a stable wake time.
- Recommend help if sleep problems persist or pair with low mood.

## Example

User: "我晚上一直睡不着。"
Reply pattern: "今晚先不逼自己立刻睡着，可以把担心写下来，设一个固定起床时间，再做 3 分钟慢呼气。"
