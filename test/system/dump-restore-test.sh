#! /bin/sh
# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

set -o errexit
set -o nounset

tmpdir=$(mktemp -d) || exit 1
lenticularis-admin dump > $tmpdir/dump
lenticularis-admin restore $tmpdir/dump                                                                                                                  
lenticularis-admin dump > $tmpdir/dump2                                                                                                                  
if diff $tmpdir/dump $tmpdir/dump2; then
	echo OK -- dump-restore test
fi
rm -r $tmpdir
