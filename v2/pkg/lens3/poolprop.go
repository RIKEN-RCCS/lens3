/* Pool Data. */

// Copyright 2022-2024 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

package lens3

import (
// "fmt"
// "flag"
// "context"
// "io"
// "log"
// "os"
// "net"
// "net/http"
// "net/http/httputil"
// "net/url"
// "math/big"
// "strings"
// "time"
// "runtime"
// "slices"
// "os/user"
)

// POOL_PROP is a description of a pool, a merge of the properties in
// the keyval-db to fully present it.
type pool_prop struct {
	pool_record       `json:"pool_record"`
	user_record       `json:"user_record"`
	pool_state_record `json:"pool_state_record"`
	Buckets           []*bucket_record `json:"buckets"`
	Secrets           []*secret_record `json:"secrets"`
}

// GATHER_POOL_PROP returns a property description of a pool.  It
// constructs a property description by gathering data scattered in
// the keyval-db.
func gather_pool_prop(t *keyval_table, pool string) *pool_prop {
	var poolprop = pool_prop{}
	var pooldata = get_pool(t, pool)
	if pooldata == nil {
		slogger.Warn("A race happens in gather_pool_prop")
		return nil
	}
	assert_fatal(pooldata.Pool == pool)
	poolprop.pool_record = *pooldata
	//
	// Check a buckets-directory entry.
	//
	var bd = find_buckets_directory_of_pool(t, pool)
	if !(pooldata.Buckets_directory == bd) {
		slogger.Error(("An inconsistent entry in keyval-db:" +
			" bad buckets-directory entry"),
			"bd1", pooldata.Buckets_directory, "bd2", bd)
	}
	//
	// Gather buckets.
	//
	var bkts = gather_buckets(t, pool)
	poolprop.Buckets = bkts
	//
	// Gather access-keys.
	//
	var keys = gather_secrets(t, pool)
	poolprop.Secrets = keys
	//
	// Set user info.
	//
	var uid = poolprop.Owner_uid
	var u = get_user(t, uid)
	if u == nil {
		slogger.Error(("An inconsistent entry in keyval-db:" +
			" user of pool nonexists"), "uid", uid, "pool", pool)
	}
	if u != nil {
		poolprop.user_record = *u
	}
	//
	// Gather dynamic states.
	//
	var state *pool_state_record = get_pool_state(t, pool)
	if state != nil {
		poolprop.pool_state_record = *state
	}
	//check_pool_is_well_formed(poolprop, None)
	return &poolprop
}

// GATHER_BUCKETS gathers buckets in a pool.  A returned list is
// sorted for displaying.
func gather_buckets(t *keyval_table, pool string) []*bucket_record {
	var bkts1 = list_buckets(t, pool)
	//slices.SortFunc(bkts1, func(x, y *bucket_record) int {
	//return strings.Compare(x.Pool, y.Pool)
	//})
	return bkts1
}

// GATHER_SECRETS gathers secrets (access key pairs) in a pool.  A
// returned list is sorted for displaying.  It excludes a probe-key
// (which is internally used).
func gather_secrets(t *keyval_table, pool string) []*secret_record {
	var keys1 = list_secrets_of_pool(t, pool)
	//slices.SortFunc(keys1, func(x, y *secret_record) int {
	//return (big.NewInt(x.Timestamp).Cmp(big.NewInt(y.Timestamp)))
	//})
	return keys1
}
