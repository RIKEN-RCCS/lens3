#!/bin/ksh -x

# Test by AWS CLI.  Tested commands are: {cp, ls, mv, rm, presign}.
# It needs shell variables "EP" (an endpoint URL) and "BKT" (a bucket
# name).  The bucket should be created and set accessible in advance.
# It leaves some garbage files in the current directory and in the
# bucket.

# It reads "copy-file-conf.sh" if it exists.  It assumes it defines
# variables EP and BKT, and also it may include variables SIZ and DBG.
# The file size SIZ should be larger than 8MB for testing a
# multipart-upload.  Set these shell variables like:
# EP=https://lens3.example.com; BKT=bkt0

if [ -f ./copy-file-conf.sh ]; then
    . ./copy-file-conf.sh
fi

if [ -z "${EP}" -o -z "${BKT}" ]; then
    echo "It needs an endpoint setting in EP"
    echo "and an existing bucket name in BKT."
    exit 1
fi

SIZ=${SIZ:-32M}
DBG=${DBG:-""}
#DBG="--no-verify-ssl --debug"
#DBG="--no-verify-ssl"

AWS="aws ${DBG} --endpoint-url ${EP}"

echo "AWS command is: ${AWS}"

echo "Generating a ${SIZ} random file..."
rm -f gomi-file0.txt
touch gomi-file0.txt
shred -n 1 -s 32M gomi-file0.txt

echo "S3-CP (upload) a file to a bucket ${BKT}..."
${AWS} s3 cp gomi-file0.txt s3://${BKT}/gomi-file1.txt
status=$?
echo "S3-CP (upload) status=$status"
if [ "$status" != "0" ]; then
    echo "S3-CP UPLOAD FAILED"
    exit 1
fi

echo "S3-CP (download) a file from a bucket ${BKT}..."
${AWS} s3 cp s3://${BKT}/gomi-file1.txt gomi-file2.txt
status=$?
echo "S3-CP (download) status=$?"

if ! cmp gomi-file0.txt gomi-file2.txt; then
    echo "gomi-file0.txt and gomi-file2.txt differ"
    echo "S3-CP DOWNLOAD FAILED"
    exit 1
fi

echo "S3-LS on a file in ${BKT}..."
${AWS} s3 ls s3://${BKT}/gomi-file1.txt
status=$?
if [ $status -ne 0 ]; then
    echo "S3-LS FAILED"
    exit 1
fi

echo "S3-MV a file in ${BKT}..."
${AWS} s3 mv s3://${BKT}/gomi-file1.txt s3://${BKT}/gomi-file3.txt
status=$?
echo "S3-MV status=$status"
if [ $status -ne 0 ]; then
    echo "S3-MV FAILED"
    exit 1
fi

${AWS} s3 ls s3://${BKT}/gomi-file3.txt
status=$?
if [ $status -ne 0 ]; then
    echo "S3-LS FAILED"
    exit 1
fi

echo "S3-PRESIGN a file in ${BKT}..."
${AWS} s3 presign s3://${BKT}/gomi-file3.txt
status=$?
if [ $status -ne 0 ]; then
    echo "presign gomi-file3.txt failed"
    exit 1
fi

echo "S3-RM a file in ${BKT}..."
${AWS} s3 rm s3://${BKT}/gomi-file3.txt
status=$?
if [ $status -ne 0 ]; then
    echo "S3-RM FAILED"
    exit 1
fi
${AWS} s3 ls s3://${BKT}/gomi-file3.txt
status=$?
if [ $status -eq 0 ]; then
    echo "removing failed; a file remains"
    exit 1
fi

# cat > index.html <<EOF
# <!DOCTYPE html>
# <html lang="en">
# <head>
# <meta charset="utf-8">
# <title>title</title>
# </head>
# <body>
# index.html
# </body>
# </html>
# EOF
# sed -e 's/index/error/' < index.html > error.html

# ${AWS} s3 cp index.html s3://${BKT}/
# status=$?
# ${AWS} s3 cp error.html s3://${BKT}/
# status=$?
#
# echo "S3-WEBSITE the ${BKT}..."
# ${AWS} s3 website s3://${BKT}/ --index-document index.html --error-document error.html
# status=$?
# if [ $status -ne 0 ]; then
#     echo "S3-WEBSITE failed"
#     exit 1
# fi

echo "Done"
