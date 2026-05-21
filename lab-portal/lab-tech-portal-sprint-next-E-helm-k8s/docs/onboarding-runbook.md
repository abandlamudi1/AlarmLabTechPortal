# Lab Tech Portal Onboarding Runbook

## 1. Bootstrap the environment
- Install Python 3.11 or later.
- Create a virtual environment and install requirements:
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```
- Copy `.env.example` to `.env` and populate:
  - `SECRET_KEY`: unique string per environment.
  - `RF_CHAMBER_BASE_URL`: optional absolute portal URL used in QR codes.

## 2. Initialize data stores
- Run `python tools/setup_datastores.py` to create `inventory.db` and `rf_chambers.db` in their respective tool directories.
- Verify databases by launching the app (`python app.py`) and confirming default table views render without errors.

## 3. Configure RF QR codes
- If deploying to staging/production, set `RF_CHAMBER_BASE_URL` to the public host (e.g., `https://portal.example.com`).
- Print a sample QR label from the RF dashboard and scan it to ensure it resolves correctly in the target environment.

## 4. Static assets
- After modifying any stylesheet (core or tool-specific), rebuild the bundle:
  ```powershell
  python tools/build_static.py
  ```
- Commit the generated `static/build/portal.css` when deploying bundled assets.

## 5. QA checklist
- Run `pytest` to confirm route and validation tests pass.
- Smoke test inventory CRUD and RF chamber add/edit flows.
- Validate accessibility basics: keyboard navigation, visible focus states, and descriptive labels on form controls.
