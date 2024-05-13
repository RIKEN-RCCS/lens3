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
	Pool_record       `json:"pool_record"`
	User_record       `json:"user_record"`
	Pool_state_record `json:"pool_state_record"`
	Buckets           map[string]*Bucket_record `json:"buckets"`
	Secrets           map[string]*Secret_record `json:"secrets"`
}

// Key_Policy is a policy to an access-key.
type Key_Policy string

const (
	Key_Policy_READWRITE Key_Policy = "readwrite"
	Key_Policy_READONLY  Key_Policy = "readonly"
	Key_Policy_WRITEONLY Key_Policy = "writeonly"
)

// Bkt_Policy is a public-access policy of a bucket
type Bkt_Policy string

const (
	Bkt_Policy_NONE     Bkt_Policy = "none"
	Bkt_Policy_UPLOAD   Bkt_Policy = "upload"
	Bkt_Policy_DOWNLOAD Bkt_Policy = "download"
	Bkt_Policy_PUBLIC   Bkt_Policy = "public"
)

// Pool_State is a state of a pool.
type Pool_State string

const (
	Pool_State_INITIAL    Pool_State = "initial"
	Pool_State_READY      Pool_State = "ready"
	Pool_State_SUSPENDED  Pool_State = "suspended"
	Pool_State_DISABLED   Pool_State = "disabled"
	Pool_State_INOPERABLE Pool_State = "inoperable"
)

// POOL_REASON is a set of constant strings of the reasons of state
// transitions.  It may include other messages from a backend server.
// POOL_REMOVED is not stored in the state of a pool.  EXEC_FAILED and
// SETUP_FAILED will be appended to another reason.
type Pool_Reason string

const (
	// Pool_State.INITIAL or Pool_State.READY.
	Pool_Reason_NORMAL Pool_Reason = "-"

	// Pool_State.SUSPENDED.
	Pool_Reason_BACKEND_BUSY Pool_Reason = "backend busy"

	// Pool_State.DISABLED.
	Pool_Reason_POOL_EXPIRED  Pool_Reason = "pool expired"
	Pool_Reason_USER_DISABLED Pool_Reason = "user disabled"
	Pool_Reason_POOL_OFFLINE  Pool_Reason = "pool offline"

	// Pool_State.INOPERABLE.
	Pool_Reason_POOL_REMOVED Pool_Reason = "pool removed"
	Pool_Reason_USER_REMOVED Pool_Reason = "user removed"
	Pool_Reason_EXEC_FAILED  Pool_Reason = "start failed: "
	Pool_Reason_SETUP_FAILED Pool_Reason = "initialization failed: "

	// Other reasons are exceptions and messages from a backend.

	Pool_Reason_POOL_DISABLED_INITIALLY_ Pool_Reason = "pool disabled initially"
)

// GATHER_POOL_DESC returns a pool record.  It constructs a record by
// gathering data scattered in a keyval-db.
func gather_pool_desc(t *keyval_table, pool string) *pool_desc {
	var pooldesc = pool_desc{}
	var desc1 = get_pool(t, pool)
	if desc1 == nil {
		logger.warnf("RACE in gather_pool_desc")
		return nil
	}
	pooldesc.Pool_record = *desc1
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
	var state *Pool_state_record = get_pool_state(t, pool)
	pooldesc.Pool_state_record = *state
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
