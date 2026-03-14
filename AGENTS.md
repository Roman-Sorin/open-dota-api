# Repository Instructions

- After every code change, create a git commit and push it to `origin` so deployed environments like `streamlit.app` receive the update.
- Do not leave completed code changes only in the local working tree.
- If a change adds a new import or runtime dependency, update `requirements.txt` in the same commit before pushing.
- After each push, verify the deployed UI shows the new `Build` hash before assuming the change is live.
- For user-reported stats bugs, add or update a regression test with the exact reported numbers before calling the fix complete.
- When changing overview/stat formulas, bump the UI overview schema/version so stale Streamlit session data is forcibly refreshed.
- After any app/UI/filter/behavior change, update the relevant `MD` documentation in the same task so the repository docs stay current.
