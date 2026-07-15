# TA Operational Baseline

This document characterizes the teaching-assistant (TA) baseline used in the study.

## Role in the Study

TA grades represent the operational human baseline for RQ1. They reflect regular course grading practice under the official rubric, not a consensus or adjudicated ground truth.

## Preparation and Orientation

Before each assignment cycle, all TAs participated in instructor-led orientation meetings at the start of the activity. These meetings clarified:

- expected code-review practices;
- how to apply the official rubric;
- the type of feedback students should receive.

The intent was to align review practices across TAs while preserving authentic course workflow.

## Complementary TA Roles

TAs performed two complementary roles:

| Role | Primary responsibility | Typical grading load |
| --- | --- | --- |
| Accompaniment TA | Follow student teams, answer questions, monitor progress | Usually the submissions of the teams they accompany |
| Reviewer TA | Assign final grades through rubric-based code review | Most of the submissions in the cohort |

Grading workload was allocated according to this division of labor. Reviewer TAs therefore tend to receive more submissions than accompaniment-focused TAs.

## Workload Distribution

Across 84 submissions and 28 anonymous TAs (`TA01`--`TA28`):

- mean workload: 3.0 submissions per TA;
- range: 1--6 submissions per TA;
- each submission was graded by exactly one TA.

The full mapping is stored in:

```text
inputs/manifests/ta_submission_assignment.csv
inputs/manifests/ta_workload_summary.csv
```

## Analysis Implications

- TA grades are pooled in the analysis; individual TA calibration is not modeled.
- TA personal identities and individual experience levels are not included in the anonymous artifact.
- TA feedback is heterogeneous and is therefore not used as the RQ2 diagnostic reference.
