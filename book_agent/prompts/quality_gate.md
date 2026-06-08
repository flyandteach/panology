# Quality Gate Reference

This document describes the scoring aggregation and threshold logic used by the Quality Gate Agent.
The Quality Gate Agent is implemented computationally (no LLM call required).

## Dimensions Evaluated

| Dimension         | Weight  | Minimum Threshold | Notes                            |
|-------------------|---------|-------------------|----------------------------------|
| Line Edit Quality | 25%     | 8.0               | From LineEditorAgent             |
| Repetition        | 25%     | 9.0               | From RepetitionCheckerAgent      |
| Continuity        | 25%     | 9.0               | Derived from repetition checker  |
| Critical Audience | 25%     | 8.5               | From AudienceCriticAgent         |
| Overall Average   | —       | 8.5               | Must meet even if all pass       |

## Pass Conditions

A section PASSES the quality gate only when ALL of the following are true:
1. Line edit score >= 8.0
2. Repetition score >= 9.0
3. Continuity score >= 9.0
4. Critical audience score >= 8.5
5. Overall average of all four >= 8.5

Failing ANY single condition triggers a revision cycle.

## Revision Targeting

When a section fails, the revision brief should target the specific failed dimensions:
- Failed line edit → Focus revision on sentence rhythm, transitions, word choice
- Failed repetition → Focus on eliminating flagged phrases and structural repetition
- Failed continuity → Focus on cross-reference with prior sections, avoid repeating prior content
- Failed audience → Focus on the weaknesses identified by the specific reader persona(s) who scored lowest

## Maximum Revision Cycles

After 5 failed revision cycles, the system presents the BEST draft (highest overall score)
to the user with a complete diagnosis, and asks whether to approve, reject, or pause.

## Score Display

Scores are displayed as:
- ✓ PASS (green/affirmed) when above threshold
- ✗ FAIL (red/denied) when below threshold
- A visual bar showing score position from 0 to 10
- The gap needed to reach threshold for failed dimensions
