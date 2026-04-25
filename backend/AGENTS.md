I'm building the backend for a simple net worth tracking app.

It supports two core functionalities:
1. Users should be able to see their current net worth. This is the sum of active tax lots plus the sum of all aggregated stock positions.
2. Users should receive emails if there is a tax loss harvesting opportunity available.

Some key rules:
- Use uv for installing packages.
- Use a logical file structure and write clean readable code.
- Keep backend code under this folder.
- Keep local secrets such as `.env` and `google_credentials.json` under this folder and out of git.
- Promptly remove any test or ad hoc scripts that are created as intermediate outputs of your work.

Additional notes:
- We use Neon as our relational database.
- We use FastAPI for the backend.
- For email sending, use SMTP with the provided credentials.
