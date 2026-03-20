# Repository Instructions

- After every code change, create a git commit and push it to `origin` so deployed environments like `streamlit.app` receive the update.
- Do not leave completed code changes only in the local working tree.
- If a change adds a new import or runtime dependency, update `requirements.txt` in the same commit before pushing.
- After each push, verify the deployed UI shows the new `Build` hash before assuming the change is live.
- For user-reported stats bugs, add or update a regression test with the exact reported numbers before calling the fix complete.
- When changing overview/stat formulas, bump the UI overview schema/version so stale Streamlit session data is forcibly refreshed.
- After any app/UI/filter/behavior change, update the relevant `MD` documentation in the same task so the repository docs stay current.
- UI labels must stay English-only. Use abbreviated labels where space is constrained, but prefer full labels when the layout has room.
- `Hero Overview` and `Detailed Turbo Stats` must stay synchronized on metric coverage, metric order, and value formatting. If a metric is added, removed, reordered, or reformatted in one, apply the same change in the other unless the task explicitly requires divergence.
- For `Hero Overview` specifically, keep column headers abbreviated. For `Detailed Turbo Stats`, use full metric labels where space allows.
- Visual meaning must stay synchronized too: if a metric is color-coded in `Hero Overview` (for example win/loss or winrate semantics), apply the same semantic color treatment in `Detailed Turbo Stats`.
