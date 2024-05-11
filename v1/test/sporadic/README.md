# Sporadic Test

## Brief Description

It keeps running uploading/downloading in some interval.
Starting/stopping of MinIO instances is the critical part in the
working of Lens3.  Set "period" in "testc.json" to match the value
"minio_awake_duration" in "mux-conf.yaml".  "fluctuation" is a percent
of a plus/minus range, and fluctuation=20 means ±20%.
