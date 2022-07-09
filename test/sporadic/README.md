# Sporadic Tests

## Brief Descriptions

Runs simple uploading/downloading in some interval. Starting/stopping
of MinIO is critical in workings of Lens3.  Set "period" in
"testc.json" to match the value "minio_awake_duration" in
"mux-config.yaml".  "fluctuation" is a percent of a plus/minus range.
fluctuation=20 means ±20%.
