# Private files and security reports

## Keep account material outside Git

The documented cookie location is `private/apple-cookies.txt`. Git ignores every `private/` directory, cookie-named files, real environment files, session files, private keys and local databases. `.env.example` templates remain versioned. These rules prevent accidental additions; they do not remove a file already tracked in Git.

Before staging changes, check locally:

```sh
git check-ignore private/apple-cookies.txt apple_music/private/apple-cookies.txt
git status --short
python -m unittest discover -s tests -v
```

CI verifies ignore behavior and checks the current tracked-file list for private/runtime paths. This filename policy is not a general secret scanner, does not inspect every string and does not prove the entire Git history is free of secrets.

The Docker build uses an explicit source allowlist and additional private-file exclusions. Pass credentials at runtime; do not put them in a Dockerfile, image layer, public build log or issue.

## If a credential is exposed

Revoke or refresh the affected token/session first. Remove the tracked file and assess history cleanup and any published artifacts separately. Adding an ignore rule alone does not revoke access or erase past commits.

Do not post tokens, cookies, account exports, private databases, signed media URLs or complete recordings in issues. Use GitHub's private vulnerability reporting if it is enabled; otherwise ask for a private contact channel without including sensitive details. No response-time guarantee is offered for this personal project.
