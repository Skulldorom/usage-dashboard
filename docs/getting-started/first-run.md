# First-run setup

The admin password is created with a one-time setup code printed to the backend
logs. There is no default password.

## Create the admin password

1. Start the stack and open the frontend.
2. The UI asks for a setup code. Get it from the backend logs:

   ```bash
   docker compose logs backend
   ```

   Look for a line like `Admin setup code: <code>`.
3. Enter the code and choose a new password in the UI.

`GET /api/v1/auth/status` generates and logs the code only when no password
exists yet, so the code never leaks before setup is complete.

## Reset the password

Password resets use the same log-based pattern:

1. Open the login page and choose **Reset password**.
2. The backend logs a one-time reset code (`Admin password reset code: <code>`).
3. Enter the code and the new password in the UI.

Both setup and reset codes expire after
`ADMIN_RECOVERY_CODE_EXPIRE_MINUTES` (default `30`).

## Session expiry

Password-login sessions expire after `ADMIN_SESSION_EXPIRE_HOURS` (default `24`).
After that, you sign in again with your admin password.
