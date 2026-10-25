# Security

RollHarbor is a local application for a trusted shared computer. It binds to
`127.0.0.1`, validates request origin/host and serves only approved public web
paths. It has no account system and should not be exposed as an Internet service.

Public APIs expose the public world and campaign. Never put DM secrets in those
files. Private folders are protected from web serving, not from filesystem access.
Save exports and screenshots can still contain private player information.

For a sensitive vulnerability, use GitHub private vulnerability reporting if it
is enabled on the repository, or the maintainer contact on the owner's profile.
Do not put secrets or exploit data from a real table in a public issue. For
ordinary bugs, provide a small synthetic reproduction.
