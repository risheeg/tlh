I'm building a simple networth tracking app.

It supports two core functionalities:
1. User should be able to see their current net worth. This is just the sum of active tax lots plus the sum of all aggreated stock positions
2. Users should recieve emails if there is a tax loss harvesting oppurtunity available

Some key rules:
- Use uv for installing packages
- Use a logical file structure and write clean readable code
- Keep all backend code under the backend folder.
- Promptly remove any test or adhoc scripts that are created as intermediate outputs of your work

Additional Notes:
- We will use Neon as our relational database
- We will use FastAPI for the backend
- For email sending, use the SMTP with the provided credentials
