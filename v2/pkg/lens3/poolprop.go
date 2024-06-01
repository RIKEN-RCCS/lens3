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
	"time"
	// "runtime"
	// "slices"
	"os/user"
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
		logger.warnf("RACE in gather_pool_prop")
		return nil
	}
	assert_fatal(pooldata.Pool == pool)
	poolprop.pool_record = *pooldata
	//
	// Check a buckets-directory entry.
	//
	var bd = find_buckets_directory_of_pool(t, pool)
	if !(pooldata.Buckets_directory == bd) {
		logger.errf("inconsistent entry found in keyval-db;"+
			" buckets-directory (%v)≠(%v)", pooldata.Buckets_directory, bd)
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
		logger.errf("inconsistent entry found in keyval-db;"+
			" user of pool nonexists uid=(%s) pool=(%s)", uid, pool)
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

// UPDATE_POOL_STATE checks the changes of user and pool settings, and
// updates the state.  This code should be called periodically.  It
// returns a pair of a state and a reason.
func update_pool_state(t *keyval_table, pool string, permitted user_approval) (pool_state, pool_reason) {
	var desc = get_pool(t, pool)
	if desc == nil {
		return pool_state_INOPERABLE, pool_reason_POOL_REMOVED
	}
	var state *pool_state_record = get_pool_state(t, pool)
	if state == nil {
		logger.errf("Mux(pool=%s): pool-state not found.", pool)
		return pool_state_INOPERABLE, pool_reason_POOL_REMOVED
	}

	switch state.State {
	case pool_state_SUSPENDED:
		return state.State, state.Reason
	case pool_state_INOPERABLE:
		return state.State, state.Reason
	default:
	}

	// Check a state transition.

	switch state.State {
	case pool_state_SUSPENDED:
		panic("internal")
	case pool_state_INOPERABLE:
		panic("internal")
	case pool_state_INITIAL:
	case pool_state_READY:
	case pool_state_DISABLED:
	default:
		panic("internal")
	}

	var uid = desc.Owner_uid
	var active, _ = check_user_is_active(t, uid)
	if !active {
		set_pool_state(t, pool, pool_state_DISABLED, state.Reason)
		return pool_state_DISABLED, pool_reason_USER_INACTIVE
	}

	var now = time.Now().Unix()
	var unexpired = !(desc.Expiration_time < now)
	var online = desc.Online_status
	var ok = (unexpired && online)
	if ok {
		if state.State == pool_state_DISABLED {
			set_pool_state(t, pool, pool_state_INITIAL, pool_reason_NORMAL)
		}
		return pool_state_INITIAL, pool_reason_NORMAL
	} else {
		var reason pool_reason
		if !unexpired {
			reason = pool_reason_POOL_EXPIRED
		} else if !online {
			reason = pool_reason_POOL_OFFLINE
		} else {
			reason = pool_reason_NORMAL
		}
		set_pool_state(t, pool, pool_state_DISABLED, reason)
		return pool_state_DISABLED, reason
	}
}

func check_user_is_active(t *keyval_table, uid string) (bool, error_message) {
	var now int64 = time.Now().Unix()
	var ui = get_user(t, uid)
	if ui == nil {
		logger.warnf("User not found: user=(%s)", uid)
		return false, message_user_not_registered
	}
	if !ui.Enabled || ui.Expiration_time < now {
		return false, message_user_disabled
	}

	var _, err1 = user.Lookup(uid)
	if err1 != nil {
		switch err1.(type) {
		case user.UnknownUserError:
		default:
		}
		logger.warnf("user.Lookup(%s) fails: err=(%v)", uid, err1)
		return false, message_no_user_account
	}
	// (uu.Uid : string, uu.Gid : string)

	return true, error_message{}
}
