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
)

type pool_desc struct {
	pool_record       `json:"pool_record"`
	User_record       `json:"user_record"`
	pool_state_record `json:"pool_state_record"`
	Buckets           map[string]*Bucket_record `json:"buckets"`
	Secrets           map[string]*Secret_record `json:"secrets"`
}

// GATHER_POOL_DESC returns a pool record.  It constructs a record by
// gathering data scattered in a keyval-db.
func gather_pool_desc(t *keyval_table, pool string) *pool_desc {
	var pooldesc = pool_desc{}
	var desc1 = get_pool(t, pool)
	if desc1 == nil {
		logger.warnf("RACE in gather_pool_desc")
		return nil
	}
	pooldesc.pool_record = *desc1
	var bd = get_buckets_directory_of_pool(t, pool)
	assert_fatal(desc1.Pool == pool)
	if !(desc1.Buckets_directory == bd) {
		logger.warnf("inconsistent entry found in keyval-db")
	}
	//
	// Gather buckets.
	//
	var bkts = gather_buckets(t, pool)
	pooldesc.Buckets = bkts
	//
	// Gather access-keys.
	//
	var keys = gather_keys(t, pool)
	pooldesc.Secrets = keys
	//
	// Set user info.
	//
	var uid = pooldesc.Owner_uid
	var u = get_user(t, uid)
	if u == nil {
		logger.warnf("inconsistent entry found in keyval-db")
	}
	if u != nil {
		pooldesc.User_record = *u
	}
	//
	// Gather dynamic states.
	//
	var state *pool_state_record = get_pool_state(t, pool)
	if state != nil {
		pooldesc.pool_state_record = *state
	}
	//check_pool_is_well_formed(pooldesc, None)
	return &pooldesc
}

// GATHER_BUCKETS gathers buckets in a pool.  A returned list is
// sorted for displaying.
func gather_buckets(t *keyval_table, pool string) map[string]*Bucket_record {
	var bkts1 = list_buckets(t, pool)
	//slices.SortFunc(bkts1, func(x, y *Bucket_record) int {
	//return strings.Compare(x.Pool, y.Pool)
	//})
	return bkts1
}

// GATHER_KEYS gathers secrets (access-keys) in a pool.  A returned
// list is sorted for displaying.  It excludes a probe-key (which is
// internally used).
func gather_keys(t *keyval_table, pool string) map[string]*Secret_record {
	var keys1 = list_secrets_of_pool(t, pool)
	//slices.SortFunc(keys1, func(x, y *Secret_record) int {
	//return (big.NewInt(x.Modification_time).Cmp(big.NewInt(y.Modification_time)))
	//})
	return keys1
}
