# ChangeLog

The list is sketchy.

## v2.2.1 2026-03

  - Change the backend server form "MinIO" to "s3-baby-server"
  - Provide RPM package
  - Patch UI to replace the name "MinIO" to non-specific "backend"
  - Correct signing method to accept unicode file names
  - Update Golang libraries

The RPM package includes the "s3-baby-server" binary to ease
installation.

This version did not rebuild UI from the source.  It just patched
strings.  It includes a fix to force an unix time value to an integer
(by floor).

Fix the proxy to use a client ip by "X-Forwarded-For".  Golang's
http.Request.RemoteAddr used to point to a client ip in Lens3-v2.1.1
(around Sep. 2024).  But, it now points to proxy's ip in Lens3-v2.2.1
(Mar. 2024).

;; Local Variables:
;; eval: (fundamental-mode)
;; End:
