# Abstract Grading Calibration

Below are generic examples (not associated with specific labs or specific domain problems) focused on guiding limit decisions (edge cases) when assigning deductions by criteria:

1. **Strong solution with a localized defect still deserves a high grade:**
   If a submission globally achieves the intention and primary modeling described in a criterion, but fails on an isolated and secondary detail whose incorrect use is localized in a single isolated method, **do not zero the domain grade and do not promote severe arbitrary penalties**. Round the points lost and record exactly why.

2. **Partial tests or suites with breaks do not automatically become zero:**
   Missing tests affect the testing criteria. They **do not invalidate the theoretical modeling if it was implemented** for the components. Do not propagate null scores to the functionality code just because the tests for it fail. Keep the penalties contained within the criteria corresponding to the tests.

3. **Nominal structure without real behavior does not sustain a high grade:**
   A student who generates required classes nominally ("stubbing") but entirely omits the business logic lines within the methods has not demonstrated proficiency in this functional criterion. In such cases, the code only exists decoratively: the penalty in its business domain is maximum.

4. **Cosmetic detail should not contaminate a central criterion:**
   Visual text formatting (e.g., "extra space in print," "uppercase vs. lowercase in toString," "variable naming"), when the rubric does not require identical cosmetic/output string pattern text, **can never decrease scores for architectural and system concepts (e.g., encapsulation, algorithms)**. Keep it clean and ignore out-of-scope rubric errors.

5. **The same root cause should not generate multiple heavy penalties:**
   If a student committed a basic but universal error in their code, find the location where this error causes class or abstraction structure damage under the most relevant criterion. The initial cause should not be re-reported under every other criterion massively penalizing the student's average. Example: the absence of dependency injection may justify severe cuts in the 'coupling/modeling' category, but do not zero specific functionalities that coincidentally would be served by and dependent on this modeling.

6. **Do not invent feedback to fill space (Stage 2 Upper Limit):**
   A brilliant student will have virtually 0 defects in the package. The score should be perfect without invented caveats that obscure readability. The feedback will be simple and focused on praise.
