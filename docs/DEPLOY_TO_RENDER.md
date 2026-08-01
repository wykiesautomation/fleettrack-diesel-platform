# Deploy FleetTrack REV08 to Render

1. Create a private GitHub repository and upload the extracted REV08 contents. Do not upload `.env`, database files, customer data or device secrets.
2. In Render, create a Blueprint or Web Service from the repository. `render.yaml` provisions the Python service and PostgreSQL database.
3. Set environment variables: PUBLIC_BASE_URL, PAYFAST_MERCHANT_ID, PAYFAST_MERCHANT_KEY and PAYFAST_PASSPHRASE. Keep PAYFAST_MODE=sandbox until all tests pass.
4. Deploy. Confirm `/health` returns REV08 and PostgreSQL.
5. Edit the PayFast sandbox configuration so return, cancel and notify URLs use the public HTTPS Render domain.
6. Test registration, login, a sandbox subscription, ITN processing, dashboard access and SIM868 API ingestion.
7. Only then change PAYFAST_MODE to live and replace all sandbox merchant values with live values.

GitHub is source control. Render is the running Python service. PostgreSQL stores persistent data.
