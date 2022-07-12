#!/bin/ksh -x

# Simple test.  It creates garbage files.  RUN IN "test/stupid".  It
# needs variables "EP", "BKT".
# Tested commands: {cp, ls, mv, rm, presign}

# A file size should be larger than 8MB for a multipart-upload.

if [ -n "${LENS3TEST}" ]; then
        . ${LENS3TEST}
fi
if [ -z "${BKT}" ]; then
    dir=`dirname -- "$0"`
    cnf=${dir}/lens3test
    if [ -f "${cnf}" -a -r "${cnf}" ]; then
        . ${cnf}
    fi
fi

#DEBUG=--debug
DEBUG=""
AWS="aws ${DEBUG} --endpoint-url ${EP}"

echo ${AWS}

SIZ=${SIZ:-32M}
echo "Generating a ${SIZ} random file..."
rm -f gomi-file0.txt
touch gomi-file0.txt
shred -n 1 -s 32M gomi-file0.txt

echo "CP (uploading) a file to a bucket ${BKT}..."
${AWS} s3 cp gomi-file0.txt s3://${BKT}/gomi-file1.txt
echo "s3 cp (upload) status=$?"

echo "CP (downloading) a file from a bucket ${BKT}..."
${AWS} s3 cp s3://${BKT}/gomi-file1.txt gomi-file2.txt
echo "s3 cp (download) status=$?"

if ! cmp gomi-file0.txt gomi-file2.txt; then
    echo "cmp gomi-file0.txt gomi-file2.txt failed"
    exit 1
fi

echo "LS on a file in ${BKT}..."
${AWS} s3 ls s3://${BKT}/gomi-file1.txt
if [ $? -ne 0 ]; then
    echo "ls gomi-file1.txt failed"
fi

echo "MV a file in ${BKT}..."
${AWS} s3 mv s3://${BKT}/gomi-file1.txt s3://${BKT}/gomi-file3.txt
echo "s3 mv status=$?"
${AWS} s3 ls s3://${BKT}/gomi-file3.txt
if [ $? -ne 0 ]; then
    echo "ls gomi-file3.txt failed"
fi

echo "PRESIGN a file in ${BKT}..."
${AWS} s3 presign s3://${BKT}/gomi-file3.txt
if [ $? -ne 0 ]; then
    echo "presign gomi-file3.txt failed"
fi

echo "RM a file from ${BKT}..."
${AWS} s3 rm s3://${BKT}/gomi-file3.txt
${AWS} s3 ls s3://${BKT}/gomi-file3.txt
if [ $? -eq 0 ]; then
    echo "removing gomi-file3.txt failed"
fi

${AWS} s3 cp index.html s3://${BKT}/
${AWS} s3 cp error.html s3://${BKT}/

echo "WEBSITE the ${BKT}..."
${AWS} s3 website s3://${BKT}/ --index-document index.html --error-document error.html
if [ $? -ne 0 ]; then
    echo "website failed"
fi

echo "done."
