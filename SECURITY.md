# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 1.4.x | yes |
| < 1.4 | no |

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's
private vulnerability reporting:

1. Open the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Include steps to reproduce, affected version and distribution.

## Scope

TURMO is a local dashboard for a USB display:

- The on-demand web editor binds to `127.0.0.1` only and refuses non-loopback
  addresses. It is not designed for network exposure.
- The display protocol is vendor-specific; crashes, unsafe parsing and
  permission problems are in scope.
- The project never needs root for the per-user setup.

## Out of scope

- Problems that require physical access to the machine or a modified display
  firmware.
- Third-party themes, configs or forks.
- Issues caused by exposing the editor against the documented local-only design.
