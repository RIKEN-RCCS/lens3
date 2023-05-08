#! /bin/sh

# Copyright (c) 2022-2023 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

set -o errexit
set -o nounset

tmpdir=$(mktemp -d) || exit 1
lens3-admin dump > $tmpdir/dump
lens3-admin restore $tmpdir/dump
lens3-admin dump > $tmpdir/dump2
if diff $tmpdir/dump $tmpdir/dump2; then
	echo OK -- dump-restore test
fi
rm -r $tmpdir
