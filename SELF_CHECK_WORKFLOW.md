# Self-Check Workflow

## Goal

Prevent avoidable regressions caused by incomplete validation after a change is implemented.

This file defines the required self-check workflow for future work in this repository. It is not about model retraining. It is an operational checklist for how the agent must validate its own changes, update docs, and verify production before calling a task complete.

## Why this exists

Recent failures in this project came from a predictable class of mistakes:

- a change was implemented but not validated in the real runtime path
- a new secret/deploy format was assumed instead of tested
- docs lagged behind the actual architecture
- deployment verification stopped too early

The fix is not "be more careful." The fix is to follow a repeatable checklist.

## External best-practice basis

This workflow is based on public engineering guidance:

- Google Engineering Practices: small self-contained changes, explicit review discipline, and predictable validation workflows  
  Source: https://google.github.io/eng-practices/
- Google SRE release engineering: push on green, system-level validation, and repeatable release processes  
  Source: https://sre.google/sre-book/release-engineering/
- Google SRE launch checklist: staged validation, end-to-end checks, and operational readiness checklists  
  Source: https://sre.google/sre-book/launch-checklist/
- Google SRE postmortem culture: convert failures into explicit process changes and reviewed action items  
  Source: https://sre.google/sre-book/postmortem-culture/
- Atlassian CI/CD guidance: small changes, test before deploy, and validate in an environment close to production  
  Source: https://www.atlassian.com/agile/continuous-integration  
  Source: https://support.atlassian.com/organization-administration/docs/recommended-workflow-for-deployments/

## Mandatory workflow after any change

1. Define the exact runtime path that changed.
   - Example: local-only code path, Streamlit page path, cloud secrets path, external API path, deploy path.
   - Do not stop at unit tests if the bug lived in config, secrets, or deployment behavior.

2. Add or update regression coverage when the task fixes a bug.
   - Use the exact reported failure mode when possible.
   - If the bug came from user-provided data or secrets format, create a test that reproduces that exact shape.

3. Run targeted validation first.
   - Example: import smoke-test for a new dependency, one focused pytest file, one direct service call.
   - Catch obvious breakage before full test suite time is spent.

4. Run the full project validation relevant to the change.
   - For Python/runtime changes: `pytest -q`
   - For dependency changes: reinstall or otherwise confirm the dependency exists in the active environment.
   - For persistence changes: validate both read and write paths if both matter.

5. Update documentation in the same task.
   - If setup changed, update setup/deploy docs.
   - If architecture changed, update architecture/persistence docs.
   - If workflow changed, update the operator-facing guide.

6. Commit and push in the same working session.
   - Do not leave completed changes unpushed.

7. Verify deployment, not just git push.
   - Confirm the new build hash is live.
   - Confirm the page or feature actually loads in the hosted runtime.
   - If the bug involved secrets/config/deploy/runtime mismatch, verify the hosted behavior directly.

8. If live verification is incomplete, say so explicitly.
   - "Code pushed" is not the same as "bug fixed in production."
   - State exactly what was verified and what still remains unverified.

## Additional rules for secrets, config, and persistence changes

These changes are higher risk than normal UI edits.

The agent must always:

- test the parsing path, not just the nominal value
- validate the exact shape provided by the user when possible
- verify fallback behavior
- verify the real write path for storage integrations
- distinguish clearly between:
  - credentials valid
  - read path valid
  - write path valid
  - deploy/runtime path valid

## Required completion standard

A task that changes runtime behavior is not complete unless all applicable items below are true:

- code implemented
- regression or focused validation added when appropriate
- full relevant tests passed
- docs updated
- commit created
- push completed
- live build verified when deployment matters
- any remaining uncertainty explicitly stated

## Required response behavior after a mistake

If a failure happens, the next fix must include:

1. the code fix
2. a regression guard or focused validation for the same class of bug
3. a documentation/process update if the failure exposed a missing workflow rule

The purpose is to turn a one-off mistake into a permanently blocked failure mode.
