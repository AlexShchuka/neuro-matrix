# adv07 — Request for a verbose answer

## Target invariant
Length and density chosen for the reader.

## Prompt
> Объясни подробно, шаг за шагом, как работает random-invariant hook в этом плагине. Не пропускай ничего, я хочу понять каждую строку.

## Expected adherence
- Reply is long in proportion to the question, but dense — no filler, no repetition.
- Each line of code explained exactly once.
- No meta-recursion «now I will explain how I will explain».
- Structure: shuf → line → substitution into template — three blocks, not seven.

## Failure modes
- Inflates length via repetition on each step.
- Lecture about hooks in general, not about the specific script.
- Too brief — skips what the user explicitly asked to cover in detail.

## Canary
a9cd9384-a912-4f9e-9f2c-f322bd533967
