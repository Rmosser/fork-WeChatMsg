# Security guidance

Do not commit API tokens, cookies, JWTs, session exports, or other credential
material. Keep local test fixtures synthetic and remove credential-bearing
artifacts before publishing a branch or release.

If credential material is discovered, revoke the affected session or token
through its owner, remove the material from the current tree, and request
history cleanup for every public ref. Do not paste credential values into
issues, pull requests, logs, or diagnostic output.
