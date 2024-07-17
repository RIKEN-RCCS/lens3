/* Accessors to the Keyval-DB (Valkey). */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// A table makes typed records from/to json in the keyval-db.  A table
// consists of a set of three databases to easy manual inspection in
// the keyval-db.
//
// NOTE: Errors related to configuration files are fatal.  Such calls
// are in the admin tool.  It calls panic(nil).

// This is for Valkey v7.2.5, and valkey-go v1.0.40.

// MEMO: Values of strings are converted by string(), not by
// valkey.BinaryString().

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"github.com/valkey-io/valkey-go"
	"slices"
	"time"
)

type keyval_table struct {
	setting       valkey.Client
	storage       valkey.Client
	process       valkey.Client
	prefix_to_db  map[string]valkey.Client
	db_name_to_db map[string]valkey.Client
	tracing       trace_flag
}

const limit_of_id_generation_loop = 30

// Prefixes attached to db keys.  The records of values corresponds to
// these prefixes.
const (
	db_conf_prefix       = "cf:"
	db_user_data_prefix  = "uu:"
	db_user_claim_prefix = "um:"

	db_pool_data_prefix = "po:"
	db_directory_prefix = "bd:"
	db_pool_name_prefix = "px:"
	db_bucket_prefix    = "bk:"
	db_secret_prefix    = "sx:"

	db_mux_ep_prefix         = "mu:"
	db_backend_data_prefix   = "de:"
	db_backend_mutex_prefix  = "dx:"
	db_csrf_token_prefix     = "tn:"
	db_pool_state_prefix     = "ps:"
	db_pool_timestamp_prefix = "pt:"
	db_user_timestamp_prefix = "ut:"
	//db_backend_ep_prefix     = "ep:"
)

// DB numbers.
const (
	setting_db = 1
	storage_db = 2
	process_db = 3
)

var prefix_to_db_number_assignment = map[string]int{
	db_conf_prefix:       setting_db,
	db_user_data_prefix:  setting_db,
	db_user_claim_prefix: setting_db,

	db_pool_data_prefix: storage_db,
	db_directory_prefix: storage_db,
	db_pool_name_prefix: storage_db,
	db_secret_prefix:    storage_db,
	db_bucket_prefix:    storage_db,

	db_mux_ep_prefix:         process_db,
	db_backend_mutex_prefix:  process_db,
	db_backend_data_prefix:   process_db,
	db_csrf_token_prefix:     process_db,
	db_pool_state_prefix:     process_db,
	db_pool_timestamp_prefix: process_db,
	db_user_timestamp_prefix: process_db,
	//db_backend_ep_prefix:       process_db,
}

// Record's constraints displays properties of an entry.  Some records
// retain a key in records.  Some records are regarded as a member of
// another record indicated by member ∈ owner.  Its members should be
// removed when an owner is removed.

// Records for configuration are defined in "conf.go".  They are
// stored under the keys: "cf:reg", "cf:mux", and "cf:mux:"+mux-name.

// "uu:"+uid Entry (db_user_data_prefix).  An ephemeral marker is
// on, when a user is added automatically at an access to the
// registrar.  Constraint: (key≡user_record.Uid).
type user_record struct {
	Uid             string   `json:"uid"`
	Claim           string   `json:"claim"`
	Groups          []string `json:"groups"`
	Enabled         bool     `json:"enabled"`
	Ephemeral       bool     `json:"ephemeral"`
	Expiration_time int64    `json:"expiration_time"`

	Check_terms_and_conditions bool  `json:"check_terms_and_conditions"`
	Timestamp                  int64 `json:"timestamp"`
}

// "tn:"+uid Entry (db_csrf_token_prefix).  A csrf_token is a pair
// of cookie+header.  Constraint: (tn:_ ∈ uu:User).
type csrf_token_record struct {
	Csrf_token []string `json:"csrf_token"`
	Timestamp  int64    `json:"timestamp"`
}

// "um:"+claim Entry (db_user_claim_prefix).
// Constraint: (um:_ ∈ uu:User).
type user_claim_record struct {
	Uid       string `json:"uid"`
	Timestamp int64  `json:"timestamp"`
}

// "px:"+pool-name Entry (db_pool_name_prefix).
// Constraint: (px:_ ∈ po:Pool).
type pool_mutex_record struct {
	Owner_uid string `json:"owner"`
	Timestamp int64  `json:"timestamp"`
}

// "po:"+pool-name Entry (db_pool_data_prefix).
// Constraint: (key≡pool_record.Pool).
type pool_record struct {
	Pool             string `json:"pool"`
	Bucket_directory string `json:"bucket_directory"`
	Owner_uid        string `json:"owner_uid"`
	Owner_gid        string `json:"owner_gid"`
	Probe_key        string `json:"probe_key"`
	Enabled          bool   `json:"enabled"`
	Expiration_time  int64  `json:"expiration_time"`
	Timestamp        int64  `json:"timestamp"`
}

// "de:"+pool-name Entry (db_backend_data_prefix).  A pair of
// root_access and root_secret is a credential for accessing a
// backend.  A state ranges only in a subset {pool_state_READY,
// pool_state_SUSPENDED}.  Timestamp is a start time.  Constraint:
// (key≡backend_record.Pool).
type backend_record struct {
	Pool        string     `json:"pool"`
	Backend_ep  string     `json:"backend_ep"`
	Backend_pid int        `json:"backend_pid"`
	State       pool_state `json:"state"`
	Root_access string     `json:"root_access"`
	Root_secret string     `json:"root_secret"`
	Mux_ep      string     `json:"mux_ep"`
	Mux_pid     int        `json:"mux_pid"`
	Timestamp   int64      `json:"timestamp"`
}

// "dx:"+pool-name Entry (db_backend_mutex_prefix).  This entry
// is temporarily created to mutex to run a single backend.
type backend_mutex_record struct {
	Mux_ep    string `json:"mux_ep"`
	Timestamp int64  `json:"timestamp"`
}

// "ps:"+pool-name Entry (db_pool_state_prefix).  Constraint:
// (key≡pool_state_record.Pool).
type pool_state_record struct {
	Pool      string      `json:"pool"`
	State     pool_state  `json:"state"`
	Reason    pool_reason `json:"reason"`
	Timestamp int64       `json:"timestamp"`
}

// "bd:"+directory Entry (db_directory_prefix).  Constraint:
// (key≡bucket_directory_record.Directory), (bd:_ ∈ po:Pool).
type bucket_directory_record struct {
	Pool      string `json:"pool"`
	Directory string `json:"directory"`
	Timestamp int64  `json:"timestamp"`
}

// "bk:"+bucket Entry (db_bucket_prefix).  Constraint:
// (key≡bucket_record.Bucket), (bk:_ ∈ po:Pool).
type bucket_record struct {
	Pool            string        `json:"pool"`
	Bucket          string        `json:"bucket"`
	Bucket_policy   bucket_policy `json:"bucket_policy"`
	Expiration_time int64         `json:"expiration_time"`
	Timestamp       int64         `json:"timestamp"`
}

// "sx:"+secret Entry (db_secret_prefix).  Constraint:
// (key≡secret_record.Access_key), (sx:_ ∈ po:Pool).
type secret_record struct {
	Pool            string        `json:"pool"`
	Access_key      string        `json:"access_key"`
	Secret_key      string        `json:"secret_key"`
	Secret_policy   secret_policy `json:"secret_policy"`
	Expiration_time int64         `json:"expiration_time"`
	Timestamp       int64         `json:"timestamp"`
}

// "mu:"+mux-ep Entry (db_mux_ep_prefix).  Constraint:
// (key≡mux_record.Mux_ep).
type mux_record struct {
	Mux_ep     string `json:"mux_ep"`
	Start_time int64  `json:"start_time"`
	Timestamp  int64  `json:"timestamp"`
}

// "pt:"+pool-name Entry (db_pool_timestamp_prefix).
// Constraint: (pt:_ ∈ po:Pool).
// type int64

// "ut:"+uid Entry (db_user_timestamp_prefix).
// Constraint: (ut:_ ∈ uu:User).
// type int64

// BUCKET_POLICY is a public-access policy attached to a bucket
// (without an access key).  "rw" is PUBLIC, "ro" is DOWNLOAD, and
// "wo" is UPLOAD.
type bucket_policy string

const (
	bucket_policy_RW   bucket_policy = "rw"
	bucket_policy_RO   bucket_policy = "ro"
	bucket_policy_WO   bucket_policy = "wo"
	bucket_policy_NONE bucket_policy = "none"
)

// SECRET_POLICY is a policy attached to an access key.
type secret_policy string

const (
	secret_policy_RW              secret_policy = "rw"
	secret_policy_RO              secret_policy = "ro"
	secret_policy_WO              secret_policy = "wo"
	secret_policy_internal_access secret_policy = "internal-access"
)

type name_timestamp_pair struct {
	Name      string `json:"name"`
	Timestamp int64  `json:"timestamp"`
}

type routing_bucket_desc_keys__ struct {
	pool              string
	bucket_policy     string
	modification_time int64
}

// KEY_PAIR is a access key and a secret key.
type key_pair struct {
	access_key string
	secret_record
}

// POOL_DIRECTORY is returned by list_bucket_directories()
type pool_directory__ struct {
	pool      string
	directory string
}

// POOL_STATE is a state of a pool.
type pool_state string

const (
	pool_state_INITIAL    pool_state = "initial"
	pool_state_READY      pool_state = "ready"
	pool_state_SUSPENDED  pool_state = "suspended"
	pool_state_DISABLED   pool_state = "disabled"
	pool_state_INOPERABLE pool_state = "inoperable"
)

// POOL_REASON is a set of reasons of state transitions.  It may
// include other messages from a backend server.  POOL_REMOVED is not
// stored in the state of a pool.  EXEC_FAILED and SETUP_FAILED will
// be appended with a specific reason.
type pool_reason string

const (
	/* Reasons for INITIAL or READY are: */

	pool_reason_NORMAL pool_reason = "-"

	/* Reasons for SUSPENDED are: */

	pool_reason_SERVER_BUSY pool_reason = "server busy"

	/* Reasons for DISABLED are: */

	pool_reason_USER_INACTIVE pool_reason = "user inactive"
	pool_reason_POOL_EXPIRED  pool_reason = "pool expired"
	pool_reason_POOL_OFFLINE  pool_reason = "pool offline"

	/* Reasons for INOPERABLE are: */

	pool_reason_POOL_REMOVED pool_reason = "pool removed"
	pool_reason_EXEC_FAILED  pool_reason = "start failed: "
	pool_reason_SETUP_FAILED pool_reason = "initialization failed: "
	//pool_reason_USER_REMOVED pool_reason = "user removed"

	// Other reasons are exceptions and messages from a backend.

	pool_reason_POOL_DISABLED_INITIALLY_ pool_reason = "pool disabled initially"
)

const db_no_expiration = 0

// MAKE_KEYVAL_TABLE makes keyval-db clients.
func make_keyval_table(conf *db_conf, tracing trace_flag) *keyval_table {
	var ep = conf.Ep
	var pw = conf.Password
	var setting, err1 = valkey.NewClient(valkey.ClientOption{
		InitAddress: []string{ep},
		Password:    pw,
		SelectDB:    setting_db,
	})
	if err1 != nil {
		slogger.Error("keyval-db client (n=1) error", "err", err1)
		panic(nil)
	}
	var storage, err2 = valkey.NewClient(valkey.ClientOption{
		InitAddress: []string{ep},
		Password:    pw,
		SelectDB:    storage_db,
	})
	if err2 != nil {
		slogger.Error("keyval-db client (n=2) error", "err", err2)
		panic(nil)
	}
	var process, err3 = valkey.NewClient(valkey.ClientOption{
		InitAddress: []string{ep},
		Password:    pw,
		SelectDB:    process_db,
	})
	if err3 != nil {
		slogger.Error("keyval-db client (n=3) error", "err", err3)
		panic(nil)
	}
	var t = &keyval_table{
		setting:       setting,
		storage:       storage,
		process:       process,
		prefix_to_db:  make(map[string]valkey.Client),
		db_name_to_db: make(map[string]valkey.Client),
		tracing:       tracing,
	}
	for k, i := range prefix_to_db_number_assignment {
		switch i {
		case setting_db:
			t.prefix_to_db[k] = setting
		case storage_db:
			t.prefix_to_db[k] = storage
		case process_db:
			t.prefix_to_db[k] = process
		default:
			panic(nil)
		}
	}
	t.db_name_to_db["setting"] = t.setting
	t.db_name_to_db["storage"] = t.storage
	t.db_name_to_db["process"] = t.process

	// Wait for a keyval-db.

	for {
		var db = t.setting
		var ctx1 = context.Background()
		//var w = db.Ping(ctx1)
		var w = db.Do(ctx1, db.B().Ping().Build())
		if w.Error() == nil {
			slogger.Debug("Connected to keyval-db", "ep", ep)
			return t
		} else {
			slogger.Debug("Connect to keyval-db failed (sleeping)")
			time.Sleep(30 * time.Second)
		}
	}
}

func raise_on_marshaling_error(err error) {
	if err != nil {
		slogger.Error("json.Marshal() on db entry failed", "err", err)
		raise(&proxy_exc{
			"-",
			http_500_internal_server_error,
			[][2]string{
				message_bad_db_entry,
			},
		})
	}
}

func raise_on_set_error(w *valkey.ValkeyResult) {
	var err = w.Error()
	if err != nil {
		slogger.Error("db-set() failed", "err", err)
		raise(&proxy_exc{
			"-",
			http_500_internal_server_error,
			[][2]string{
				message_bad_db_entry,
			}})
	}
}

func raise_on_setnx_error(w *valkey.ValkeyResult) {
	var err = w.Error()
	if err != nil {
		slogger.Error("db-setnx() failed", "err", err)
		raise(&proxy_exc{
			"-",
			http_500_internal_server_error,
			[][2]string{
				message_bad_db_entry,
			}})
	}
}

// RAISE_ON_GET_ERROR raises on an error except for a non-existing
// case.  Existence of an entry is double checked in unmarshaling.
func raise_on_get_error(w *valkey.ValkeyResult) {
	var err = w.Error()
	if err != nil && !valkey.IsValkeyNil(err) {
		slogger.Error("db-get() failed", "err", err)
		raise(&proxy_exc{
			"-",
			http_500_internal_server_error,
			[][2]string{
				message_bad_db_entry,
			}})
	}
}

func check_on_del_failure(w *valkey.ValkeyResult) bool {
	var n, err = w.AsInt64()
	if err != nil {
		slogger.Error("db-del() failed", "err", err)
		raise(&proxy_exc{
			"-",
			http_500_internal_server_error,
			[][2]string{
				message_bad_db_entry,
			}})
	}
	return n == 1
}

func raise_on_del_failure(w *valkey.ValkeyResult) {
	var n, err = w.AsInt64()
	if err != nil {
		slogger.Error("db-del() failed", "err", err)
		raise(&proxy_exc{
			"-",
			http_500_internal_server_error,
			[][2]string{
				message_bad_db_entry,
			}})
	}
	if n != 1 {
		slogger.Error("db-del() no entry")
		raise(&proxy_exc{
			"-",
			http_500_internal_server_error,
			[][2]string{
				message_bad_db_entry,
			}})
	}
}

// CHECK_ON_EXPIRE_FAILURE raises on an error except for a
// non-existing case.  It returns NG when a key does not exist.
func check_on_expire_failure(w *valkey.ValkeyResult) bool {
	var ok, err = w.AsBool()
	if err != nil {
		slogger.Error("db-expire() failed", "err", err)
		raise(&proxy_exc{
			"-",
			http_500_internal_server_error,
			[][2]string{
				message_bad_db_entry,
			}})
	}
	return ok
}

/* CONF */

func set_conf(t *keyval_table, conf lens3_conf) {
	switch conf1 := conf.(type) {
	case *mux_conf:
		var sub = conf1.Subject
		if !(sub == "mux" || (len(sub) >= 5 && sub[:4] == "mux:")) {
			slogger.Error("Bad conf; subject≠mux")
			panic(nil)
		}
		//fmt.Println("set mux-conf")
		db_set_with_prefix(t, db_conf_prefix, sub, conf1)
	case *reg_conf:
		var sub = conf1.Subject
		if !(sub == "reg") {
			slogger.Error("Bad conf; subject≠reg")
			panic(nil)
		}
		//fmt.Println("set reg-conf")
		db_set_with_prefix(t, db_conf_prefix, sub, conf1)
	default:
		slogger.Error("Bad conf; type≠mux_conf nor type≠reg_conf",
			"type", fmt.Sprintf("%T", conf))
		panic(nil)
	}
}

func delete_conf(t *keyval_table, sub string) {
	db_del_with_prefix(t, db_conf_prefix, sub)
}

// LIST_CONFS returns a list of confs.  It contains both mux_conf and
// reg_conf.
func list_confs(t *keyval_table) []*lens3_conf {
	var prefix = db_conf_prefix
	var confs []*lens3_conf = make([]*lens3_conf, 0)
	var ee = scan_table(t, prefix, "*")
	for _, k := range ee {
		var sub = k[len(prefix):]
		var v lens3_conf
		switch {
		case sub == "mux" || (len(sub) >= 5 && sub[:4] == "mux:"):
			v = get_mux_conf(t, sub)
		case sub == "reg":
			v = get_reg_conf(t, sub)
		default:
			slogger.Error("Bad subject name", "name", sub)
			panic(nil)
		}
		if v != nil {
			confs = append(confs, &v)
		}
	}
	return confs
}

func get_mux_conf(t *keyval_table, sub string) *mux_conf {
	assert_fatal(sub == "mux" || (len(sub) >= 5 && sub[:4] == "mux:"))
	var data mux_conf
	var ok = db_get_with_prefix(t, db_conf_prefix, sub, &data)
	if ok {
		check_mux_conf(&data)
	}
	return ITE(ok, &data, nil)
}

func get_reg_conf(t *keyval_table, sub string) *reg_conf {
	assert_fatal(sub == "reg")
	var data reg_conf
	var ok = db_get_with_prefix(t, db_conf_prefix, sub, &data)
	if ok {
		check_reg_conf(&data)
	}
	return ITE(ok, &data, nil)
}

// ADD_USER adds/modifies a user and its claim entry.  A duplicate
// claim is an error.
func add_user(t *keyval_table, u *user_record) {
	assert_fatal(u.Uid != "")
	assert_fatal(len(u.Groups) > 0)
	var uid = u.Uid
	var claim = u.Claim
	if claim != "" {
		var claiminguser = get_user_claim(t, claim)
		if claiminguser != nil && claiminguser.Uid != uid {
			slogger.Error("Bad conflicting uid claims",
				"claim", claim, "uid1", uid, "uid2", claiminguser.Uid)
			raise(&proxy_exc{
				"-",
				http_500_internal_server_error,
				[][2]string{
					message_user_account_conflict,
				}})
		}
		var now int64 = time.Now().Unix()
		var data = &user_claim_record{
			Uid:       u.Uid,
			Timestamp: now,
		}
		set_user_claim(t, claim, data)
	}
	set_user_raw(t, u)
}

// (Use add_user() instead).
func set_user_raw(t *keyval_table, u *user_record) {
	var uid = u.Uid
	assert_fatal(uid != "")
	db_set_with_prefix(t, db_user_data_prefix, uid, &u)
}

// GET_USER gets a user by a uid.  It may return nil.
func get_user(t *keyval_table, uid string) *user_record {
	var data user_record
	var ok = db_get_with_prefix(t, db_user_data_prefix, uid, &data)
	return ITE(ok, &data, nil)
}

// DELETE_USER deletes a user and its associated claim entry.
func delete_user(t *keyval_table, uid string) {
	var u = get_user(t, uid)
	if u == nil {
		return
	}
	db_del_with_prefix(t, db_user_data_prefix, uid)
	var claim = u.Claim
	if claim != "" {
		delete_user_claim(t, claim)
		clear_user_claim(t, uid)
	}
}

// LIST_USERS lists all uid's.
func list_users(t *keyval_table) []string {
	var prefix = db_user_data_prefix
	var users []string = make([]string, 0)
	var ee = scan_table(t, prefix, "*")
	for _, k := range ee {
		var key = k[len(prefix):]
		users = append(users, key)
	}
	return users
}

func set_user_claim(t *keyval_table, claim string, uid *user_claim_record) {
	db_set_with_prefix(t, db_user_claim_prefix, claim, uid)
}

// GET_CLAIM_USER maps a claim to a uid, or returns nil.
func get_user_claim(t *keyval_table, claim string) *user_claim_record {
	assert_fatal(claim != "")
	var data user_claim_record
	var ok = db_get_with_prefix(t, db_user_claim_prefix, claim, &data)
	return ITE(ok, &data, nil)
}

func delete_user_claim(t *keyval_table, claim string) {
	db_del_with_prefix(t, db_user_claim_prefix, claim)
}

// CLEAR_USER_CLAIM deletes a claim associated to an uid.  It scans
// all the claims.  (This is paranoiac because it is called after
// deleting a claim entry).
func clear_user_claim(t *keyval_table, uid string) {
	var prefix = db_user_claim_prefix
	var db = t.prefix_to_db[prefix]
	var ee = scan_table(t, prefix, "*")
	for _, k := range ee {
		var key = k[len(prefix):]
		var claiminguser = get_user_claim(t, key)
		if claiminguser.Uid == uid {
			if trace_db_set&t.tracing != 0 {
				slogger.Debug("DB: del", "key", k)
			}
			var ctx1 = context.Background()
			//var w = db.Del(ctx1, k)
			var w = db.Do(ctx1, db.B().Del().Key(k).Build())
			raise_on_del_failure(&w)
		}
	}
}

/* POOL */

func set_pool(t *keyval_table, pool string, data *pool_record) {
	assert_fatal(data.Pool == pool)
	db_set_with_prefix(t, db_pool_data_prefix, pool, data)
}

func get_pool(t *keyval_table, pool string) *pool_record {
	var data pool_record
	var ok = db_get_with_prefix(t, db_pool_data_prefix, pool, &data)
	return ITE(ok, &data, nil)
}

func delete_pool(t *keyval_table, pool string) {
	db_del_with_prefix(t, db_pool_data_prefix, pool)
}

// LIST_POOLS returns a list of all pool-names when the argument is
// pool="*".  Or, it checks the existence of a pool.
func list_pools(t *keyval_table, pool string) []string {
	var prefix = db_pool_data_prefix
	var pools []string = make([]string, 0)
	var ee = scan_table(t, prefix, pool)
	for _, k := range ee {
		var key = k[len(prefix):]
		pools = append(pools, key)
	}
	return pools
}

// SET_EX_BUCKET_DIRECTORY atomically sets a directory for buckets.
// It returns OK or NG.  On a failure, it returns a current owner in
// the tuple 2nd, as (false,pool).  A returned pool can be "" due to a
// race.
func set_ex_bucket_directory(t *keyval_table, path string, dir *bucket_directory_record) (bool, string) {
	assert_fatal(dir.Directory == path)
	var ok = db_setnx_with_prefix(t, db_directory_prefix, path, dir)
	if ok {
		return true, ""
	}
	// Race, return failure.
	var holder = get_bucket_directory(t, path)
	var holder_pool string
	if holder != nil {
		holder_pool = holder.Pool
	} else {
		holder_pool = ""
	}
	return false, holder_pool
}

func get_bucket_directory(t *keyval_table, path string) *bucket_directory_record {
	var data bucket_directory_record
	var ok = db_get_with_prefix(t, db_directory_prefix, path, &data)
	return ITE(ok, &data, nil)
}

func find_bucket_directory_of_pool(t *keyval_table, pool string) string {
	var prefix = db_directory_prefix
	var ee = scan_table(t, prefix, "*")
	for _, k := range ee {
		var path = k[len(prefix):]
		var dir = get_bucket_directory(t, path)
		if dir != nil && dir.Pool == pool {
			return path
		}
	}
	return ""
}

func delete_bucket_directory_checking(t *keyval_table, path string) bool {
	var ok = db_del_with_prefix(t, db_directory_prefix, path)
	return ok
}

// LIST_BUCKET_DIRECTORIES lists all bucket-directories.
func list_bucket_directories(t *keyval_table) []*bucket_directory_record {
	var prefix = db_directory_prefix
	var dirs []*bucket_directory_record = make([]*bucket_directory_record, 0)
	var ee = scan_table(t, prefix, "*")
	for _, k := range ee {
		var path = k[len(prefix):]
		var dir = get_bucket_directory(t, path)
		if dir != nil {
			dirs = append(dirs, dir)
			// bkts = append(bkts, &pool_directory{
			// 	pool:      dir.Pool,
			// 	directory: path,
			// })
		}
	}
	return dirs
}

func set_pool_state__(t *keyval_table, pool string, state pool_state, reason pool_reason) {
	var now int64 = time.Now().Unix()
	var data = &pool_state_record{
		Pool:      pool,
		State:     state,
		Reason:    reason,
		Timestamp: now,
	}
	set_pool_state_raw(t, pool, data)
}

func set_pool_state_raw(t *keyval_table, pool string, state *pool_state_record) {
	db_set_with_prefix(t, db_pool_state_prefix, pool, state)
}

func get_pool_state__(t *keyval_table, pool string) *pool_state_record {
	var data pool_state_record
	var ok = db_get_with_prefix(t, db_pool_state_prefix, pool, &data)
	return ITE(ok, &data, nil)
}

func delete_pool_state__(t *keyval_table, pool string) {
	db_del_with_prefix(t, db_pool_state_prefix, pool)
}

// SET_EX_BACKEND_MUTEX makes an exclusion entry for a backend.  It
// returns OK or NG.  It tries to return an old record, but it can be
// null due to a race (but practically never).
func set_ex_backend_mutex(t *keyval_table, pool string, data *backend_mutex_record) (bool, *backend_mutex_record) {
	var ok = db_setnx_with_prefix(t, db_backend_mutex_prefix, pool, data)
	if ok {
		return true, nil
	}
	// Race, return failure.
	var holder = get_backend_mutex(t, pool)
	return false, holder
}

func set_backend_mutex_expiry(t *keyval_table, pool string, timeout time.Duration) bool {
	var sec int64 = duration_in_sec(timeout)
	var ok = db_expire_with_prefix(t, db_backend_mutex_prefix, pool, sec)
	return ok
}

func get_backend_mutex(t *keyval_table, pool string) *backend_mutex_record {
	var data backend_mutex_record
	var ok = db_get_with_prefix(t, db_backend_mutex_prefix, pool, &data)
	return ITE(ok, &data, nil)
}

func delete_backend_mutex(t *keyval_table, pool string) {
	db_del_with_prefix(t, db_backend_mutex_prefix, pool)
}

func set_backend(t *keyval_table, pool string, data *backend_record) {
	assert_fatal(data.Pool == pool)
	db_set_with_prefix(t, db_backend_data_prefix, pool, data)
}

func set_backend_expiry(t *keyval_table, pool string, timeout time.Duration) bool {
	var sec int64 = duration_in_sec(timeout)
	var ok = db_expire_with_prefix(t, db_backend_data_prefix, pool, sec)
	return ok
}

func get_backend(t *keyval_table, pool string) *backend_record {
	var data backend_record
	var ok = db_get_with_prefix(t, db_backend_data_prefix, pool, &data)
	return ITE(ok, &data, nil)
}

func delete_backend(t *keyval_table, pool string) {
	db_del_with_prefix(t, db_backend_data_prefix, pool)
}

// LIST_BACKENDS returns a list of all currently running backends.
// Use "*" for pool.
func list_backends(t *keyval_table, pool string) []*backend_record {
	var prefix = db_backend_data_prefix
	var procs []*backend_record = make([]*backend_record, 0)
	var ee = scan_table(t, prefix, pool)
	for _, k := range ee {
		var id = k[len(prefix):]
		var p = get_backend(t, id)
		if p != nil {
			procs = append(procs, p)
		}
	}
	return procs
}

func set_mux_ep(t *keyval_table, mux_ep string, data *mux_record) {
	assert_fatal(data.Mux_ep == mux_ep)
	db_set_with_prefix(t, db_mux_ep_prefix, mux_ep, data)
}

func set_mux_ep_expiry(t *keyval_table, mux_ep string, timeout time.Duration) bool {
	var sec int64 = duration_in_sec(timeout)
	var ok = db_expire_with_prefix(t, db_mux_ep_prefix, mux_ep, sec)
	return ok
}

func get_mux_ep(t *keyval_table, mux_ep string) *mux_record {
	var data mux_record
	var ok = db_get_with_prefix(t, db_mux_ep_prefix, mux_ep, &data)
	return ITE(ok, &data, nil)
}

func delete_mux_ep(t *keyval_table, mux_ep string) {
	db_del_with_prefix(t, db_mux_ep_prefix, mux_ep)
}

// LIST_MUX_EPS returns a list of Mux-record.
func list_mux_eps(t *keyval_table) []*mux_record {
	var prefix = db_mux_ep_prefix
	var muxs []*mux_record = make([]*mux_record, 0)
	var ee = scan_table(t, prefix, "*")
	for _, k := range ee {
		var ep = k[len(prefix):]
		var d = get_mux_ep(t, ep)
		if d != nil {
			muxs = append(muxs, d)
		}
	}
	return muxs
}

// SET_EX_BUCKET atomically sets a bucket.  It returns OK or NG.
// On a failure, it returns a current owner in the tuple 2nd, as
// (false,pool).  A returned pool can be "" due to a race.
func set_ex_bucket(t *keyval_table, bucket string, data *bucket_record) (bool, string) {
	assert_fatal(data.Bucket == bucket)
	var ok = db_setnx_with_prefix(t, db_bucket_prefix, bucket, data)
	if ok {
		return true, ""
	}
	// Race, return failure.
	var holder = get_bucket(t, bucket)
	var holder_pool string
	if holder != nil {
		holder_pool = holder.Pool
	} else {
		holder_pool = ""
	}
	return false, holder_pool
}

func get_bucket(t *keyval_table, bucket string) *bucket_record {
	var data bucket_record
	var ok = db_get_with_prefix(t, db_bucket_prefix, bucket, &data)
	return ITE(ok, &data, nil)
}

func delete_bucket_checking(t *keyval_table, bucket string) bool {
	var ok = db_del_with_prefix(t, db_bucket_prefix, bucket)
	return ok
}

// LIST_BUCKETS lists buckets.  If pool≠"", lists buckets for a pool.
func list_buckets(t *keyval_table, pool string) []*bucket_record {
	var prefix = db_bucket_prefix
	var bkts []*bucket_record = make([]*bucket_record, 0)
	var ee = scan_table(t, prefix, "*")
	for _, k := range ee {
		var key = k[len(prefix):]
		var d = get_bucket(t, key)
		if d == nil {
			continue
		}
		assert_fatal(d.Bucket == key)
		if pool == "" || d.Pool == pool {
			bkts = append(bkts, d)
		}
	}
	return bkts
}

func set_pool_timestamp(t *keyval_table, pool string) {
	var now int64 = time.Now().Unix()
	db_set_with_prefix(t, db_pool_timestamp_prefix, pool, now)
}

func get_pool_timestamp(t *keyval_table, pool string) int64 {
	var data int64
	var ok = db_get_with_prefix(t, db_pool_timestamp_prefix, pool, &data)
	return ITE(ok, data, 0)
}

func delete_pool_timestamp(t *keyval_table, pool string) {
	db_del_with_prefix(t, db_pool_timestamp_prefix, pool)
}

// LIST_POOL_TIMESTAMPS returns a list of (pool-id, ts) pairs.
func list_pool_timestamps(t *keyval_table) []*name_timestamp_pair {
	var poollist = list_pools(t, "*")
	var pairs []*name_timestamp_pair = make([]*name_timestamp_pair, 0)
	for _, pool := range poollist {
		var ts = get_pool_timestamp(t, pool)
		if ts == 0 {
			slogger.Debug("intenal: list_pool_timestamps failed",
				"pool", pool)
			continue
		}
		pairs = append(pairs, &name_timestamp_pair{pool, ts})
	}
	return pairs
}

func clean_pool_timestamps(t *keyval_table) {
	var poollist = list_pools(t, "*")
	var prefix = db_pool_timestamp_prefix
	var ee = scan_table(t, prefix, "*")
	for _, k := range ee {
		var pool = k[len(prefix):]
		if !slices.Contains(poollist, pool) {
			slogger.Error("clean_pool_timestamps() Remove remaining entry",
				"pool", pool)
			delete_pool_timestamp(t, pool)
		}
	}
}

func set_user_timestamp(t *keyval_table, uid string) {
	var now int64 = time.Now().Unix()
	db_set_with_prefix(t, db_user_timestamp_prefix, uid, now)
}

// It returns 0 on an internal db-access error.
func get_user_timestamp(t *keyval_table, uid string) int64 {
	var data int64
	var ok = db_get_with_prefix(t, db_user_timestamp_prefix, uid, &data)
	return ITE(ok, data, 0)
}

func delete_user_timestamp(t *keyval_table, uid string) {
	db_del_with_prefix(t, db_user_timestamp_prefix, uid)
}

// LIST_USER_TIMESTAMPS returns a list of (uid, ts) pairs.
func list_user_timestamps(t *keyval_table) []*name_timestamp_pair {
	var userlist = list_users(t)
	var pairs []*name_timestamp_pair = make([]*name_timestamp_pair, 0)
	for _, uid := range userlist {
		var ts = get_user_timestamp(t, uid)
		if ts == 0 {
			slogger.Debug("intenal: list_user_timestamps failed",
				"user", uid)
			continue
		}
		pairs = append(pairs, &name_timestamp_pair{uid, ts})
	}
	return pairs
}

func clean_user_timestamps(t *keyval_table) {
	var userlist = list_users(t)
	var prefix = db_user_timestamp_prefix
	var ee = scan_table(t, prefix, "*")
	for _, k := range ee {
		var uid = k[len(prefix):]
		if !slices.Contains(userlist, uid) {
			slogger.Error("clean_user_timestamps() remove a remaining entry",
				"user", uid)
			delete_user_timestamp(t, uid)
		}
	}
}

// SET_WITH_UNIQUE_POOL_NAME makes a random unique id for a pool-name or an
// access key.
func set_with_unique_pool_name(t *keyval_table, data *pool_mutex_record) string {
	var prefix = db_pool_name_prefix
	var s = set_with_unique_id_loop(t, prefix, data, generate_random_key)
	return s
}

// SET_WITH_UNIQUE_SECRET_KEY makes a random unique id for a an
// access key.  The generator function assigns a new access key in
// each loop.
func set_with_unique_secret_key(t *keyval_table, data *secret_record) string {
	var generator = func() string {
		var id = generate_access_key()
		data.Access_key = id
		return id
	}
	var prefix = db_secret_prefix
	var s = set_with_unique_id_loop(t, prefix, data, generator)
	return s
}

func set_with_unique_id_loop(t *keyval_table, prefix string, data any, generator func() string) string {
	var db = t.prefix_to_db[prefix]
	var counter = 0
	for {
		var id = generator()
		if trace_db_set&t.tracing != 0 {
			slogger.Debug("DB: setnx", "key", (prefix + id))
		}
		var v, err = json.Marshal(data)
		raise_on_marshaling_error(err)
		var k = (prefix + id)
		var ctx1 = context.Background()
		//var w = db.SetNX(ctx1, k, v, db_no_expiration)
		var w = db.Do(ctx1, db.B().Setnx().Key(k).Value(string(v)).Build())
		raise_on_setnx_error(&w)
		var ok, _ = w.AsBool()
		if ok {
			return id
		}
		// Retry.
		counter += 1
		if !(counter < limit_of_id_generation_loop) {
			slogger.Error("Unique key generation failed (fatal)")
			panic(nil)
		}
	}
}

// SET_EX_POOL_MUTEX is used in restoring the keyval-db.
func set_ex_pool_mutex(t *keyval_table, pool string, data *pool_mutex_record) bool {
	var ok = db_setnx_with_prefix(t, db_pool_name_prefix, pool, data)
	return ok
}

func get_pool_mutex(t *keyval_table, pool string) *pool_mutex_record {
	var data pool_mutex_record
	var ok = db_get_with_prefix(t, db_pool_name_prefix, pool, &data)
	return ITE(ok, &data, nil)
}

func delete_pool_mutex_checking(t *keyval_table, pool string) bool {
	var ok = db_del_with_prefix(t, db_pool_name_prefix, pool)
	return ok
}

// SET_EX_SECRET is used in restoring the keyval-db.
func set_ex_secret(t *keyval_table, key string, data *secret_record) bool {
	var ok = db_setnx_with_prefix(t, db_secret_prefix, key, data)
	return ok
}

func get_secret(t *keyval_table, key string) *secret_record {
	var data secret_record
	var ok = db_get_with_prefix(t, db_secret_prefix, key, &data)
	return ITE(ok, &data, nil)
}

// DELETE_SECRET_KEY deletes a access key, unconditionally.
func delete_secret_key_checking(t *keyval_table, key string) bool {
	var ok = db_del_with_prefix(t, db_secret_prefix, key)
	return ok
}

func delete_secret_key__(t *keyval_table, key string) {
	var prefix = db_secret_prefix
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var ctx1 = context.Background()
	//var w = db.Del(ctx1, k)
	var w = db.Do(ctx1, db.B().Del().Key(k).Build())
	raise_on_del_failure(&w)
}

// LIST_SECRETS_OF_POOL lists secrets (access keys) of a pool.  It
// includes a probe-key (which is created and used internally).
func list_secrets_of_pool(t *keyval_table, pool string) []*secret_record {
	var prefix = db_secret_prefix
	var secrets []*secret_record = make([]*secret_record, 0)
	var ee = scan_table(t, prefix, "*")
	for _, k := range ee {
		var key = k[len(prefix):]
		var d = get_secret(t, key)
		if d == nil {
			// Race.  It is not an error.
			continue
		}
		if d.Pool != pool {
			continue
		}
		// d.Access_key = key
		secrets = append(secrets, d)
	}
	return secrets
}

func set_csrf_token(t *keyval_table, uid string, token *csrf_token_record) {
	db_set_with_prefix(t, db_csrf_token_prefix, uid, token)
}

func set_csrf_token_expiry(t *keyval_table, uid string, timeout time.Duration) bool {
	var sec int64 = duration_in_sec(timeout)
	var ok = db_expire_with_prefix(t, db_csrf_token_prefix, uid, sec)
	return ok
}

func get_csrf_token(t *keyval_table, uid string) *csrf_token_record {
	var data csrf_token_record
	var ok = db_get_with_prefix(t, db_csrf_token_prefix, uid, &data)
	return ITE(ok, &data, nil)
}

func db_set_with_prefix(t *keyval_table, prefix string, key string, val any) {
	if trace_db_set&t.tracing != 0 {
		slogger.Debug("DB: set", "key", (prefix + key))
	}
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var v, err = json.Marshal(val)
	raise_on_marshaling_error(err)
	var ctx1 = context.Background()
	//var w = db.Set(ctx1, k, v, db_no_expiration)
	var w = db.Do(ctx1, db.B().Set().Key(k).Value(string(v)).Build())
	raise_on_set_error(&w)
}

func db_setnx_with_prefix(t *keyval_table, prefix string, key string, val any) bool {
	if trace_db_set&t.tracing != 0 {
		slogger.Debug("DB: setnx", "key", (prefix + key))
	}
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var v, err = json.Marshal(val)
	raise_on_marshaling_error(err)
	var ctx1 = context.Background()
	//var w = db.SetNX(ctx1, k, v, db_no_expiration)
	var w = db.Do(ctx1, db.B().Setnx().Key(k).Value(string(v)).Build())
	raise_on_setnx_error(&w)
	var ok, _ = w.AsBool()
	return ok
}

func db_get_with_prefix(t *keyval_table, prefix string, key string, val any) bool {
	if trace_db_get&t.tracing != 0 {
		slogger.Debug("DB: get", "key", (prefix + key))
	}
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var ctx1 = context.Background()
	//var w = db.Get(ctx1, k)
	var w = db.Do(ctx1, db.B().Get().Key(k).Build())
	raise_on_get_error(&w)
	var ok = load_db_data(&w, val)
	return ok
}

func db_expire_with_prefix(t *keyval_table, prefix string, key string, sec int64) bool {
	if trace_db_set&t.tracing != 0 {
		slogger.Debug("DB: expire", "key", (prefix + key), "sec", sec)
	}
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var ctx1 = context.Background()
	//var w = db.Expire(ctx1, k, sec)
	var w = db.Do(ctx1, db.B().Expire().Key(k).Seconds(sec).Build())
	var ok = check_on_expire_failure(&w)
	return ok
}

// DB_DEL_WITH_PREFIX returns OK/NG, but usually, failure is ignored.
func db_del_with_prefix(t *keyval_table, prefix string, key string) bool {
	if trace_db_set&t.tracing != 0 {
		slogger.Debug("DB: del", "key", (prefix + key))
	}
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var ctx1 = context.Background()
	//var w = db.Del(ctx1, k)
	var w = db.Do(ctx1, db.B().Del().Key(k).Build())
	var ok = check_on_del_failure(&w)
	return ok
}

// DB_DEL_WITH_PREFIX raises, when delete failed.
func db_del_with_prefix_raise__(t *keyval_table, prefix string, key string) {
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var ctx1 = context.Background()
	//var w = db.Del(ctx1, k)
	var w = db.Do(ctx1, db.B().Del().Key(k).Build())
	raise_on_del_failure(&w)
}

// LOAD_DATA fills a structure by json data in the keyval-db.  It
// returns true or false about an entry is found.  Note that a get
// with valkey.IsValkeyNil(err) means a non-exising entry.
func load_db_data(w *valkey.ValkeyResult, data any) bool {
	var b, err1 = w.AsBytes()
	if err1 != nil {
		if valkey.IsValkeyNil(err1) {
			return false
		} else {
			slogger.Error("Bad value in keyval-db", "err", err1)
			raise(&proxy_exc{
				"-",
				http_500_internal_server_error,
				[][2]string{
					message_bad_db_entry,
				}})
		}
	}

	// if false {
	// 	switch s := data.(type) {
	// 	case *string:
	// 		*s = string(b)
	// 		return true
	// 	}
	// }

	var r = bytes.NewReader(b)
	var d = json.NewDecoder(r)
	d.DisallowUnknownFields()
	var err2 = d.Decode(data)
	if err2 != nil {
		slogger.Error("json.Decode failed", "err", err2)
		raise(&proxy_exc{
			"-",
			http_500_internal_server_error,
			[][2]string{
				message_bad_db_entry,
			}})
	}
	return true
}

// SCAN_TABLE lists keys for the prefix+target pattern, where
// target="*" is a wildcard.  The returned keys include the prefix.
// Note that a null-ness check should be performed when getting a
// value for a key, because a deletion can intervene scanning keys and
// getting values.
func scan_table(t *keyval_table, prefix string, target string) []string {
	if trace_db_get&t.tracing != 0 {
		slogger.Debug("DB: scan", "key", (prefix + target))
	}
	var db = t.prefix_to_db[prefix]
	var pattern = prefix + target
	//var prefix_length = len(prefix)
	var ctx1 = context.Background()
	//db.Scan(ctx1, 0, pattern, 0).Iterator()
	var ee []string = make([]string, 0)
	var cur uint64 = 0
	for {
		var w = db.Do(ctx1, db.B().Scan().Cursor(cur).Match(pattern).Build())
		var e, err = w.AsScanEntry()
		if err != nil {
			slogger.Error("Scan in keyval-db failed", "err", err)
			panic(nil)
		}
		ee = append(ee, e.Elements...)
		if e.Cursor == 0 {
			break
		}
		cur = e.Cursor
	}
	return ee
}

// CLEAR-TABLES.

// CLEAR_EVERYTHING clears the keyval-db.  It leaves entries except
// entres of confs.
func clear_everything(t *keyval_table) {
	for prefix, db := range t.prefix_to_db {
		if prefix == db_conf_prefix {
			continue
		}
		clear_db(t, db, prefix)
	}
}

func clear_db(t *keyval_table, db valkey.Client, prefix string) {
	assert_fatal(len(prefix) == 3)
	var pattern = (prefix + "*")
	//var w1 = db.Scan(ctx1, 0, pattern, 0).Iterator()
	var cur uint64 = 0
	for {
		var ctx1 = context.Background()
		var w1 = db.Do(ctx1, db.B().Scan().Cursor(cur).Match(pattern).Build())
		var e, err1 = w1.AsScanEntry()
		if err1 != nil {
			slogger.Error("Scan in keyval-db failed (ignored)", "err", err1)
			return
		}
		for _, k := range e.Elements {
			var ctx2 = context.Background()
			//var _ = db.Del(ctx2, k)
			var w2 = db.Do(ctx2, db.B().Del().Key(k).Build())
			var err2 = w2.Error()
			if err2 != nil {
				slogger.Error("Del in keyval-db failed (ignored)", "err", err2)
			}
			//raise_when_db_fail(w.Err())
		}
		if e.Cursor == 0 {
			break
		}
		cur = e.Cursor
	}
}

// DB_RAW_TABLE returns a keyval-db for a db-name: {"setting",
// "storage", "process"}.
func db_raw_table(t *keyval_table, name string) valkey.Client {
	var db, ok = t.db_name_to_db[name]
	if !ok {
		slogger.Error("Bad keyval-db name", "name", name)
		return nil
	}
	return db
}

// SET_DB_RAW sets key-value in the keyval-db intact.
func set_db_raw(t *keyval_table, kv [2]string) {
	if kv[0] == "" || kv[1] == "" {
		slogger.Error("Empty keyval to keyval-db", "kv", kv)
		panic(nil)
	}
	var prefix = kv[0][:3]
	var db = t.prefix_to_db[prefix]
	if db == nil {
		slogger.Error("Bad prefix to keyval-db", "prefix", prefix)
		panic(nil)
	}
	var ctx1 = context.Background()
	//var w = db.Set(ctx1, kv[0], kv[1], db_no_expiration)
	var w = db.Do(ctx1, db.B().Set().Key(kv[0]).Value(kv[1]).Build())
	raise_on_set_error(&w)
}

func adm_del_db_raw(t *keyval_table, key string) {
	if key == "" {
		slogger.Error("Empty key to keyval-db")
		panic(nil)
	}
	for name, db := range t.db_name_to_db {
		var ctx1 = context.Background()
		//var w = db.Del(ctx1, key)
		var w = db.Do(ctx1, db.B().Del().Key(key).Build())
		var n, err = w.AsInt64()
		if err == nil && n == 1 {
			fmt.Printf("deleted (%s) in %s in keyval-db\n", key, name)
		}
	}
}

// SCAN_DB_RAW returns a list of all entries in the keyval-db.  It
// returns an empty list for a bad db name (not an error).
func scan_db_raw(t *keyval_table, dbname string) []map[string]string {
	var db = db_raw_table(t, dbname)
	if db == nil {
		return []map[string]string{}
	}
	var keyvals = make([]map[string]string, 0)
	var cur uint64 = 0
	for {
		var ctx1 = context.Background()
		//db.Scan(ctx1, 0, "*", 0).Iterator()
		var w = db.Do(ctx1, db.B().Scan().Cursor(cur).Match("*").Build())
		var e, err = w.AsScanEntry()
		if err != nil {
			slogger.Error("Scan in keyval-db failed (ignored)", "err", err)
			return []map[string]string{}
		}
		var kvs = make_key_value_pairs(t, db, e.Elements)
		keyvals = append(keyvals, kvs...)
		if e.Cursor == 0 {
			break
		}
		cur = e.Cursor
	}
	return keyvals
}

// MAKE_KEY_VALUE_PAIRS makes key-value pairs from the key list.  It
// returns an array of maps, with each map a single key-value entry.
func make_key_value_pairs(t *keyval_table, db valkey.Client, ee []string) []map[string]string {
	var keyvals []map[string]string
	for _, k := range ee {
		var ctx1 = context.Background()
		//var w = db.Get(ctx1, k)
		var w = db.Do(ctx1, db.B().Get().Key(k).Build())
		var val, err1 = w.AsBytes()
		if err1 != nil {
			// w.Error() case subsumed.
			if valkey.IsValkeyNil(err1) {
				continue
			} else {
				slogger.Error("Get in keyval-db failed", "err", err1)
				panic(nil)
			}
		}
		keyvals = append(keyvals, map[string]string{k: string(val)})
	}
	return keyvals
}
