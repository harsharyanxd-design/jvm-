JVM SHYAMALI PORTAL
===================

LOCAL REVIEW
------------
Requires Python 3.10 or newer. From this folder, run:

    python app_server.py --port 8000

Then open http://127.0.0.1:8000. The local server uses private_data/school.sqlite3.
Keep the server running while using the local site.

PUBLIC DEPLOYMENT
-----------------
The current website and API are served from one origin. For shared, persistent
data, the updated project supports PostgreSQL through the DATABASE_URL environment
variable. Review DEPLOYMENT_GUIDE.md for the Render setup, safe migration of the
SQLite database, export/import of old browser-local edits, credentials, privacy,
and the cross-device verification checklist.

PRIVATE FILES
-------------
The project archive includes student data and seed credentials in private_data/.
Keep the archive and working files private. The Dockerfile copies only website
runtime files and app_server.py; it excludes private_data and the old standalone
portal. Do not use a public repository or static-only hosting for this project.

The old jvm_shyamali_portal.html file is retained as a local recovery/export tool.
It uses browser localStorage and is not the production website. Do not publish it.

LIMITATIONS
-----------
- The active site has same-origin APIs; CORS and a separate API URL are not needed.
- Login sessions are held in server memory, so keep one web-service instance.
  A restart may sign users out, but PostgreSQL data remains.
- Contact enquiries are stored for master review; the form does not send email.
- Payment processing is disabled until a school-approved provider is integrated.
- The chatbot can use the built-in FAQ; external AI/model access is optional.

No public deployment has been made by this project update. A Render account,
private source repository, managed database, approved school credentials, and
deployment are required to create the public URL.
