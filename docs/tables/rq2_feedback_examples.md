# RQ2: Representative Diagnostic Examples

Qualitative examples omitted from the PDF body (`tab:feedback_examples`).
They illustrate aggregate RQ2 patterns with matched issues, unmatched reports arising from code-review expectations beyond the rubric, and missed pedagogically relevant issues.

| Case | Expert-reference issue | Model behavior | Interpretation |
| --- | --- | --- | --- |
| S01, basic functionality | Expert: Adding to List from empty position should report “POSIÇÃO INVÁLIDA”. Deducted 2.0 points. | **GPT-5.5**: Bundled with related issues in 1.0-pt deduction. **Gemini**: Did not report this specific issue. | GPT detected but grouped; Gemini missed entirely. Shows variation in diagnostic coverage between models. |
| S01, readability | Expert: No issue reported in readability criterion (full score). | **GPT-5.5**: Deducted points for imprecise Javadoc comments and literal numbers. **Gemini**: Also deducted for documentation clarity. | Both models applied more rigorous documentation standards than expert rubric. Shows models prioritizing code quality beyond assignment scope. |
| S02, array usage | Expert: Not subtracting 1 from user position when accessing arrays. Deducted 3.5 points. | **GPT-5.5**: Did not identify this off-by-one error. **Gemini**: Correctly identified the array indexing issue. | GPT missed concrete bug; Gemini caught it. Shows complementary strengths. |
