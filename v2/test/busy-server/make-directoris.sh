#!/bin/ksh

# This creates a number of directories needed to run the test.
# Directories are named "pool" + nnn, and they are created in the
# specified pool-pool directory.  Arguments are: pool-pool-directory
# number-of-directories.

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 pool-pool-directory number-of-directories"
    exit 2
fi

d=$1
n=$2
for i in `seq 0 $(( ${n} - 1 ))` ; do
    x=$(printf "pool%03d" ${i})
    mkdir ${d}/${x}
done
