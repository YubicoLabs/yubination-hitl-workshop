# YubiNation: Human-in-the-Loop Agent Authorization Workshop

Preloop sits between an agent and its tools and can require human approval before
an agent uses a tool. In this workshop, request a customer upgrade from Standard
to VIP, approve it with a YubiKey, and confirm that the change happened.

## Before you start

- Install and start Docker Desktop with Docker Compose v2 or later.
- Use a current version of Google Chrome.
- Have internet access for the first build to download images and dependencies.
- Have a passkey-capable YubiKey and its PIN.
- Download and extract this repository (**Code → Download ZIP**), or use your
  existing clone. Open a terminal in the folder containing `compose.json`.
  Git is needed only if you clone the repository.

The Docker commands below work in macOS terminals and Windows PowerShell.
Python, Node.js and Go are not needed for this path.

## Start the workshop

1. Build and start the local services:

   ```sh
   docker compose -f compose.json up --build -d
   ```

2. Check the services:

   ```sh
   docker compose -f compose.json ps
   ```

   Open http://localhost:8080/api/v1/health in Chrome. Look for `status: healthy`
   and `database: connected` in the response, then open http://localhost:8080.
   If the health response is not ready, allow startup to finish and inspect the logs:

   ```sh
   docker compose -f compose.json logs api console
   ```

3. Choose **Sign up for the workshop**, fill in the form, and select
   **Create account**. Signup codes are disabled locally. After signing in, select
   **Open workshop →** on the dashboard or open
   http://localhost:8080/console/workshop/yubination directly.

Keep the hostname `localhost` for passkeys; do not substitute a LAN IP.

## Follow the main journey

Follow the workshop page to register your approval key, connect an agent or choose
the browser alternative, and request **Standard → VIP**. The browser alternative
needs no model API key; connecting a real agent is optional and uses your own setup.
Both paths use your registered passkey for the approval ceremony.

After approving, wait for the tool result, then use **Check current status** or
your agent’s `get_customer_status`. Success means the tool returned **VIP** and the
separate readback also shows **VIP**. Approval alone does not establish execution.
The optional [receipt lab](docs/receipt-lab.md) explains how to verify the
cryptographic approval evidence.

## Optional paths

Post-quantum passkeys are an optional challenge. See the challenge for supported
hardware and browser requirements.

- [CLI setup and onboarding](cli/README.md)
- [PreviewSign developer quickstart](integrations/previewsign/docs/DEVELOPER-QUICKSTART.md)
  — source build; no prebuilt PreviewSign installers are included.
- [Receipt lab and offline verification](docs/receipt-lab.md)

## Stop and resume

Stop the workshop, preserving local data:

```sh
docker compose -f compose.json down
```

Resume later from the same folder:

```sh
docker compose -f compose.json up -d
```

<details>
<summary>Destructive reset: erase all local workshop data</summary>

**Warning:** removing the volumes irreversibly erases all local workshop data,
including accounts, approvals and customer changes.

```sh
docker compose -f compose.json down --volumes
```

</details>

## Troubleshooting

If startup fails, confirm Docker Desktop is running and check the logs above.
If ports 8080 or 8000 are already in use, create a file named `.env` beside
`compose.json` with two unused ports, for example:

```dotenv
WORKSHOP_PORT=8081
WORKSHOP_API_PORT=8001
```

Apply the change:

```sh
docker compose -f compose.json up -d
```

Then open http://localhost:8081. Keep `localhost` as the hostname.

## Attribution

Based on selected public [Preloop](https://github.com/preloop/preloop) upstream
revision `b44b90944258f5c9547e923e7d000ed828d0a9a9`, with YubiNation workshop additions;
this is not a full upstream mirror. See [LICENSE](LICENSE) for the upstream
Apache-2.0 terms. Retain copyright notices and PreviewSign’s separate license
and scope notices.
