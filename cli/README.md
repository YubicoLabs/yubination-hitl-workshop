# Native Preloop CLI

From this checkout, install Go 1.24 or newer (see go.mod). Network access to the
public Go module proxy is required for the dependencies pinned in go.mod/go.sum.
From the repository root:

```sh
cd cli
go build -mod=readonly -o build/preloop ./cmd/preloop
./build/preloop --help
./build/preloop signup --loopback --url http://localhost:8000 --frontend-url http://localhost:8080
./build/preloop auth status
./build/preloop agents discover --no-onboard-prompt
```

Use `login` instead of `signup` for an existing account. Match both ports to your
Compose configuration. Keep localhost for passkeys. `make build` is an alternative
requiring Make; its version fields use Git when available and fall back without it.

Discovery alone does not enroll an agent. `agents enroll openclaw --dry-run` or
`agents enroll hermes --dry-run` previews configuration changes; omit `--dry-run`
only when you intend enrollment. Enrollment creates credentials and local backups.
Agent Control additionally requires its separately installed runtime plugin;
this source candidate does not bundle those runtime plugins. Browser fixture use
requires neither plugin nor a worker. Keep CLI credentials out of source control.
See [local startup](../README.md). Platform/runtime validation is still pending.

Upstream copyright and the repository LICENSE remain applicable.
