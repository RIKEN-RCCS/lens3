Overview of Lens3
----

# Configuration

```
reverse-proxy <==> multiplexer <==> MinIO
                               <==> MinIO
                               <==> MinIO
              <==> web-ui
```

* Setting described in "setup.md"
  * Web-UI listens on port=8003 for the reverse-proxy
  * Multiplexer listens on port=8004 for the reverse-proxy
