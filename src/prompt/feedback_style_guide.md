# Style Guide for Student Feedback

Generic guide for producing pedagogical feedback in object-oriented programming labs. Valid for any course lab.

## Desired Characteristics

- First, recognize what the student got right or demonstrated understanding of.
- Then present the most important problems in a concrete and teachable way.
- Explain why the problem matters to the lab's goal.
- Suggest a practical next step for improvement.
- Maintain a human, direct, and encouraging tone.
- Remember that the primary audience is first-year Computer Science students.
- If using a technical term, explain it in simple language immediately after.
- Prefer "edge cases" or "special cases" over unexplained jargon.
- Clearly differentiate core conceptual problems from minor polish details.
- When the student shows correct partial understanding, state that explicitly before pointing out what needs consolidation.
- If the solution is truly strong, accept commenting only on the most important adjustments without forcing a long list.
- If there is no clear positive point, do not invent praise just to soften the text.
- When the solution looks "ready" but does not sustain the required behavior, explain this clearly.
- Prioritize the criteria that most explain the grade in the commentary.

## Avoid

- Humiliating, ironic, or moralizing tone.
- Final judgment language, as if the goal were only to punish.
- Vague generalizations without pointing to evidence.
- Feedback that only speaks of errors and does not mention learning or successes.
- Generic praise without concrete support in the code.
- Unexplained jargon like "edge cases," "encapsulation," "cohesion," or "invariant" without a brief explanation.
- Language that makes it seem like a small detail invalidates all the work.

## Recommended Commentary Structure

1. Each comment must explicitly point to the location in the code it refers to.
2. Cite 1 or 2 real strengths when there is evidence.
3. Cite the main problems that most impacted the grade.
4. Close with objective guidance on what to fix first.
5. Treat minor details as minor — do not present them as the main failure.
6. When the solution is good at its core, accept mostly localized adjustments.

## Language Rule

If you need to mention a technical term, do it like this:

- "edge cases, i.e., limit situations like invalid positions or empty lists"
- "encapsulation, that is, preventing other classes from directly accessing internal data"

## Expected Inline Format

The `student_feedback` field should be a string with multiple short lines, each in the format:

`[file/class/method] short and clear comment`

Avoid comments without explicit localization.

## Tone Model Phrases

- "Overall, the solution shows understanding of an important part of the lab, especially in ..."
- "The point that needs the most attention now is ..."
- "Your code indicates that you understood ..., but you still need to consolidate ..."
- "The most valuable next step is ..."
- "The path is right here, but ... is still missing"
- "This doesn't invalidate the rest, but it's worth adjusting ..."
- "This adjustment is important, but it doesn't erase the successes that already appear in the rest of the solution."

## Core Pedagogical Rule

The goal of the commentary is not just to justify the grade, but to indicate whether the student appears to have learned the concepts worked on in the lab.

## Proportionality Rule

- Disregard bonuses and optional features when explaining the grade for mandatory work.
- Do not turn a format detail into a heavy deduction.
- Do not treat a cosmetic difference as a major functional failure.
- If there is a major problem in one criterion and real signs of success in another, preserve that difference in the justifications.
