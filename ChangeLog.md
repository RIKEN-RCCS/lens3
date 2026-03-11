# ChangeLog

The list is sketchy.

## v2.2.1 2026-03

  - Change the main backend form "MinIO" to "s3-baby-server"
  - Provide RPM packaging
  - Patch UI to replace the name "MinIO" to non-specific "backend"
  - Correct signing method to accept unicode file names
  - Update Golang libraries

The package includes the "s3-baby-server" binary to ease installation.

For UI, this did not rebuild UI from the source.  It just patched
strings.

The Golangs stdlib used in v2.1.1 was reported to be with
vulnerability.

;; Local Variables:
;; eval: (fundamental-mode)
;; End:
