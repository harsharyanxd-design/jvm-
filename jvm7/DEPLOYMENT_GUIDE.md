# JVM Shyamali portal: shared-data deployment

## What the inspection found

The project is a static HTML/CSS/JavaScript website served by a custom Python HTTP server. The server already has same-origin APIs, role checks, salted PBKDF2 password hashes, and a SQLite database. The current server binds to `127.0.0.1`, stores the database at `private_data/school.sqlite3`, and seeds accounts from private JSON files. That makes the current setup local to one computer. The archived `jvm_shyamali_portal.html` is an older standalone version that saves edits in that browser's `localStorage`.

The production configuration in this update uses the existing Python server with managed PostgreSQL. The frontend already calls relative paths such as `/api/login`, so the website and API share the public origin; no localhost API address or cross-origin CORS rule is needed. The Docker image contains only the runtime website files and server code. Private seed files and the old recovery page are excluded.

The SQLite file in the supplied ZIP contains 668 student rows, 1,357 accounts, and no audit or enquiry rows at the time of inspection. The included migration copies records, account hashes, audit events, enquiries, and a private baseline used by the older-browser import flow. It refuses to merge into a non-empty PostgreSQL database and verifies row counts before committing.

## Keep the source data private

The ZIP and this updated project still contain the supplied student information and seed credentials under `private_data/` so the original data can be migrated. Keep the ZIP and working folder private. Use a private source repository; do not publish the ZIP, seed files, SQLite database, or `jvm_shyamali_portal.html` in a public repository or static site. `.gitignore` and the Dockerfile exclude those files for a fresh repository/build, but they do not remove files already committed to Git history.

Before real school use, the school must confirm that it is authorized to host these records and replace any supplied/demo account credentials with approved credentials. The current site does not include a self-service password-change screen. Do not distribute the supplied seed credentials as production credentials.

## Export edits from the old browser-only page, if needed

Do this on the original computer and in the browser profile that contains the old local changes. If you have no local-only edits, skip to the database migration.

1. Open the old `jvm_shyamali_portal.html` page in the same browser profile and at the same file path/origin where the edits were made. Browser storage is origin-specific. If the page was moved, preserve a copy and place the updated exporter page at the original location before opening it.
2. Select **Export saved portal data**. The export contains only fields that differ from that old page's built-in data, and it removes password fields. The export still contains private student information; keep it offline and private.
3. Place the downloaded JSON file in a private working folder beside the project.
4. From the project root, run:

   ```text
   python import_legacy_browser_export.py "C:\path\to\jvm-shyamali-local-data-export.json"
   ```

5. Confirm the number shown by typing the exact `IMPORT ... EXPORTED RECORDS` phrase. The importer matches existing IDs, imports changed fields only, ignores password fields and unknown IDs, writes an audit event, and creates a timestamped safety copy of the SQLite database. Review the changed/skipped counts before continuing.

This merge is done before the SQLite-to-PostgreSQL copy so browser edits and existing server-side changes reach the shared database together. The original browser storage and the SQLite source remain in place. If the active local `index.html` already reaches the local Python API, its existing master-login migration can first move same-origin browser edits into SQLite.

## Deploy on Render

Render is a suitable fit for this Python server and PostgreSQL setup. The Render web service must listen on `0.0.0.0` and its `PORT`; the Dockerfile handles that. The website and API are deployed together, and PostgreSQL is configured only in the server environment. Render documents managed PostgreSQL, web services, and internal connection URLs in its [Postgres guide](https://render.com/docs/postgresql), [web service guide](https://render.com/docs/web-services), and [connection guide](https://render.com/docs/postgresql-creating-connecting).

1. Create a **private** Git repository from the updated project folder. Check the files staged for commit and confirm `private_data/`, `original-student-records.json`, and `jvm_shyamali_portal.html` are not included. If any were committed earlier, use a fresh private repository or remove them from Git history before deployment.
2. In Render, create a managed PostgreSQL database in the region you plan to use for the web service. Choose a paid database for production; Render says free Postgres databases expire after 30 days. Create the web service in the same region.
3. Install the project's Python dependency locally if needed:

   ```text
   python -m pip install -r requirements.txt
   ```

4. Run the one-time migration from the project root:

   ```text
   python migrate_sqlite_to_postgres.py --source private_data/school.sqlite3 --seeds private_data/seed_students.json
   ```

   When prompted, paste the PostgreSQL **external** connection URL from Render's database dashboard. The prompt hides the URL. Use Render's TLS-enabled external URL when running this command from your computer. The script opens SQLite read-only, requires an empty destination, asks for a typed confirmation, and checks row counts. It does not print or save the connection URL.

   If the active local server has a newer SQLite database than the ZIP snapshot, pass that actual database path with `--source` (and use the same original seed file with `--seeds`). Do not replace a newer database with the ZIP copy.
5. In Render, create a Docker web service from the private repository, or apply the included `render.yaml`. Set these environment values in the Render dashboard:

   - `DATABASE_URL`: the database's **internal** connection URL (same region only; keep it out of the repository).
   - `JVM_SECURE_COOKIES`: `true`.

   The service listens on Render's `PORT` and checks `/healthz`. Keep one web-service instance: login sessions are currently stored in process memory. A service restart may sign users out, but PostgreSQL records remain saved.
6. Deploy. Render will show the public `onrender.com` URL after the deploy succeeds. Open that URL on a second device and sign in with school-approved credentials.

The included Render `starter` web-service plan and paid managed database have provider costs. Check the current [Render pricing](https://render.com/pricing) before creating resources. Do not use a free Postgres database for production data.

## Existing local data and ongoing use

- The SQLite-to-PostgreSQL tool copies the database snapshot. It does not delete or modify the source SQLite database.
- The separate browser export/import steps above are required only for data still stored in the old standalone page's browser. The export is a delta against that page's original data, preventing its older sample records from overwriting newer records in the v3 database.
- Keep the original ZIP, the local SQLite database, and the generated pre-import backup until the deployed records have been reviewed. Delete temporary export files securely after verification.
- Once deployed, each device reads and writes the same PostgreSQL database through the server. A change on another device appears after reloading that device's page or signing in again.
- Student record reads are scoped by role. Creating and deleting student records is restricted to the master role; create uses `POST /api/student-record` with a record and student/parent passwords, update uses `PATCH /api/student-record?student_id=...`, and delete uses `DELETE /api/student-record?student_id=...`. The current UI supports its existing sign-in and teacher/master editing flows; record creation/deletion are master-only API operations.
- Contact enquiries are stored in PostgreSQL but are not emailed. Payment processing remains disabled until a school-approved provider is configured.

## Post-deployment verification checklist

1. Open the generated public URL on a computer and a phone; both should load the same site.
2. Open `/healthz`; it should return `{"ok":true}`.
3. Sign in on device A with an approved test account. Make a reversible test edit and save it.
4. Sign in or reload on device B. Confirm it sees the saved change. Refresh both devices and confirm it remains.
5. From the master account, create a test student through the master-only API. Confirm the student and parent accounts can read only that student's record. Delete the test record and confirm its two accounts can no longer sign in.
6. Confirm a student/parent cannot edit records, a teacher cannot edit outside the assigned scope, and an unrelated origin is rejected.
7. Restart/redeploy the web service and confirm the saved record is still in PostgreSQL; users may need to sign in again because sessions are in memory.
8. Confirm the original computer can be shut down while the deployed website remains available.

No public deployment is included in this project update. The Render account, private repository, authorized school credentials, and a successful deployment are still required before a public URL exists.
