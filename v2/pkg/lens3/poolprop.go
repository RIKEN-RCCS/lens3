/* Pool Data. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Description of a pool is spread in entries in the keyval-db, and
// GATHER_POOL_PROP() collects the data from the entries.  It is
// called by Registrar and admin tools.

import (
	"cmp"
	"slices"
	"strings"
)

// POOL_PROP is a description of a pool, a merge of the properties in
// the keyval-db to fully present it.
type pool_prop struct {
	pool_record       `json:"pool_record"`
	pool_state_record `json:"pool_state_record"`
	user_record       `json:"user_record"`
	Buckets           []*bucket_record `json:"buckets"`
	Secrets           []*secret_record `json:"secrets"`
}

// GATHER_POOL_PROP reconstructs properties of a pool to display the
// pool in Web-UI via Registrar.  It reconstructs properties by
// gathering data scattered in the keyval-db.  It returns nil when the
// pool is gone.
func gather_pool_prop(t *keyval_table, pool string) *pool_prop {
	var inconsistent_db_entires = false
	var poolprop = pool_prop{}
	var pooldata = get_pool(t, pool)
	if pooldata == nil {
		slogger.Error("Inconsistency in keyval-db: no requested pool",
			"pool", pool)
		return nil
	}
	assert_fatal(pooldata.Pool == pool)
	poolprop.pool_record = *pooldata

	// Check a bucket-directory entry.

	var bd = find_bucket_directory_of_pool(t, pool)
	if !(pooldata.Bucket_directory == bd) {
		slogger.Error("Inconsistency in keyval-db: bad bucket-directory",
			"pool", pool, "bd", bd, "need", pooldata.Bucket_directory)
		inconsistent_db_entires = true
	}

	// Gather buckets.

	var bkts = gather_buckets(t, pool)
	poolprop.Buckets = bkts

	// Gather access-keys.

	var keys = gather_secrets(t, pool)
	poolprop.Secrets = keys

	// Set user info.

	var uid = poolprop.Owner_uid
	var u = get_user(t, uid)
	if u == nil {
		slogger.Error("Inconsistency in keyval-db: pool without an owner",
			"pool", pool, "old-owner", uid)
		inconsistent_db_entires = true
	}
	poolprop.user_record = *u

	// Check the state of a pool.

	var state1, reason1 = check_pool_is_usable(t, pooldata)
	var state2, reason2 = check_pool_is_suspened(t, pool)
	var state, reason = combine_pool_state(state1, reason1, state2, reason2)

	poolprop.pool_state_record = pool_state_record{
		Pool:      pool,
		State:     state,
		Reason:    reason,
		Timestamp: 0,
	}

	if inconsistent_db_entires {
		deregister_pool_by_prop(t, &poolprop)
		return nil
	}

	return &poolprop
}

// GATHER_BUCKETS reconstructs a list of buckets in a pool.
func gather_buckets(t *keyval_table, pool string) []*bucket_record {
	var bkts1 = list_buckets(t, pool)
	if false {
		slices.SortFunc(bkts1, func(x, y *bucket_record) int {
			return strings.Compare(x.Bucket, y.Bucket)
		})
	}
	return bkts1
}

// GATHER_SECRETS reconstructs a list of secrets (access key pairs) in
// a pool.  It excludes an internally used probe-key.
func gather_secrets(t *keyval_table, pool string) []*secret_record {
	var keys1 = list_secrets_of_pool(t, pool)
	if false {
		slices.SortFunc(keys1, func(x, y *secret_record) int {
			return cmp.Compare(x.Timestamp, y.Timestamp)
		})
	}
	return keys1
}
