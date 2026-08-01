# FleetTrack Diesel REV08 Cloud Deployment + PayFast Sandbox

GitHub-ready and Render-ready cloud baseline using Flask, Gunicorn, PostgreSQL and PayFast Sandbox.

Local development: create a virtual environment, install `requirements.txt`, copy `.env.example` to `.env`, set values, then run `flask --app app run`. Production uses `render.yaml` and Gunicorn.

PayFast credentials and device secrets must be environment variables and must never be committed. Sandbox must pass before live mode.

Copyright: © 2026 JP Van Wyk. All rights reserved.
