# Configuration of services in Lenticluaris-S3
----


```
reverse-proxy <-->︎ multiplexer <--> MinIO
                               <--> MinIO
                               <--> MinIO
              <--> web-ui
```

## Notes

It does not support:

* notifications
* STS
