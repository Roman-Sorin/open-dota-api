# Repository Instructions

- After every code change, create a git commit and push it to `origin` so deployed environments like `streamlit.app` receive the update.
- Do not leave completed code changes only in the local working tree.
- If a change adds a new import or runtime dependency, update `requirements.txt` in the same commit before pushing.
- After each push, verify the deployed UI shows the new `Build` hash before assuming the change is live.
