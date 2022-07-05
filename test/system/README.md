# Simple Tests

## Prerequisite

boto3

## Tests in test.yaml

```
tests:
- cleanup_pool
- test_api_manipulation
- test_public_access
- test_keytype
- test_create_bucket
- test_list_objects
- test_object_xfr
- test_object_xfr_spray
```

Run "apitest.py" first, and then run "s3test.py".

## Brief Descriptions

* Tests include one sending a false csrf_token.

### apitest.py

It tests API operations: pool creation/deletion, access-key
creation/deletion, and bucket creation/deletion.

### s3test.py

It tests S3 operations: file upload/download with varying bucket
policies and access-key policies.

### test_object_xfr

Upload and download medium sized object (2 x 256 MiB)

### test_object_xfr_spray

Upload and download many number of small sized object (32 x 512 kiB)


## Single User Test

To run system test for a user, run main.py with desired user and

      password.
      For example, the following command run tests defined in `test.yaml`
      with user `u0000`.

      ```
      $ python3 main.py --user=u0000
      ```

### Simultaneous Access Test

    - Python script `main.py` for different users may be executed
      simultaneously.
      Set number of users to be run simultaneously, to the variable
      `nu` at the beginning of `run-parallel-test`.

    - The following command runs parallel system test:
      ```
      $ ./run-parallel-test
      ```

  + Diagnosis
    `main.py` produces simple test report, each line a test name and
    the result of the test.  All test should be marked `OK`.

    In addition to functionality check, `test_object_xfr` and
    `test_object_xfr_spray` reports file transfer throughput.

## Performace Test

  - To setup forformace test environment, refer system test settings above.

  - consult makefile. perf1 is single access performace test.
    perf2 through perf8 are multi user access performace test.
    ```
    $ make perf1
    $ make perf2
    ...
