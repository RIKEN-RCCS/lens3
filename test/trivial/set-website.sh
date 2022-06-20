#!/bin/ksh -x

# Simple test.  RUN IN "test/stupid".  It needs variables "EP", "BKT".
# Tested commands: {website}

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

${AWS} s3 cp index.html s3://${BKT}
${AWS} s3 cp error.html s3://${BKT}

echo "WEBSITE the ${BKT}..."
${AWS} s3 website s3://${BKT}/ --index-document index.html --error-document error.html
if [ $? -eq 0 ]; then
    echo "website failed"
fi

echo "done."
