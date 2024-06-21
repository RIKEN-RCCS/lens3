/* Accessors to the Keyval-DB (Valkey/Redis). */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// A table makes typed records from/to json in the keyval-db.  A table
// consists of a set of three databases to easy manual inspection in
// the keyval-db.
//
// NOTE: Errors related to configuration files are fatal.  They are in
// the admin tool.  It calls panic(nil).

// This is by "go-redis/v8".  Use "go-redis/v8" for Redis-6, and
// "go-redis/v9" for Redis-7.

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"github.com/go-redis/redis/v8"
	"time"
	//"log"
	//"reflect"
)

type keyval_table struct {
	setting       *redis.Client
	storage       *redis.Client
	process       *redis.Client
	ctx           context.Context
	prefix_to_db  map[string]*redis.Client
	db_name_to_db map[string]*redis.Client
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

	db_mux_ep_prefix            = "mu:"
	db_backend_data_prefix      = "de:"
	db_backend_exclusion_prefix = "dx:"
	db_csrf_token_prefix        = "tn:"
	db_pool_state_prefix        = "ps:"
	db_pool_timestamp_prefix    = "pt:"
	db_user_timestamp_prefix    = "us:"
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

	db_mux_ep_prefix:            process_db,
	db_backend_exclusion_prefix: process_db,
	db_backend_data_prefix:      process_db,
	db_csrf_token_prefix:        process_db,
	db_pool_state_prefix:        process_db,
	db_pool_timestamp_prefix:    process_db,
	db_user_timestamp_prefix:    process_db,
	//db_backend_ep_prefix:       process_db,
}

// Records for configuration are defined in "conf.go".  They are
// "cf:reg", "cf:mux", and "cf:mux:" + mux-name.

// "uu:" + uid Entry (DB_USER_DATA_PREFIX).  Constraint:
// (key≡user_record.Uid).  An ephemeral marker is on, when a user is
// added automatically at an access to the registrar.
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

// "tn:" + uid Entry (db_csrf_token_prefix).  A csrf_token is a pair
// of cookie+header.
type csrf_token_record struct {
	Csrf_token []string `json:"csrf_token"`
	Timestamp  int64    `json:"timestamp"`
}

// "um:" + claim Entry (DB_USER_CLAIM_PREFIX).
type user_claim_record struct {
	Uid       string `json:"uid"`
	Timestamp int64  `json:"timestamp"`
}

// "px:" + pool-name Entry (DB_POOL_NAME_PREFIX).
type pool_mutex_record struct {
	Owner_uid string `json:"owner"`
	Timestamp int64  `json:"timestamp"`
}

// "po:" + pool-name Entry (DB_POOL_DATA_PREFIX).
// Constraint: (key≡pool_record.Pool).
type pool_record struct {
	Pool              string `json:"pool"`
	Buckets_directory string `json:"buckets_directory"`
	Owner_uid         string `json:"owner_uid"`
	Owner_gid         string `json:"owner_gid"`
	Probe_key         string `json:"probe_key"`
	Online_status     bool   `json:"online_status"`
	Expiration_time   int64  `json:"expiration_time"`
	Timestamp         int64  `json:"timestamp"`
}

// "de:" + pool-name Entry (DB_BACKEND_DATA_PREFIX).  A pair of
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

// "dx:" + pool-name Entry (DB_BACKEND_EXCLUSION_PREFIX).  This entry
// is temporarily created to mutex to run a single backend.
type backend_exclusion_record struct {
	Mux_ep    string `json:"mux_ep"`
	Timestamp int64  `json:"timestamp"`
}

// "ps:" + pool-name Entry (DB_POOL_STATE_PREFIX).  Constraint:
// (key≡pool_state_record.Pool).
type pool_state_record struct {
	Pool      string      `json:"pool"`
	State     pool_state  `json:"state"`
	Reason    pool_reason `json:"reason"`
	Timestamp int64       `json:"timestamp"`
}

// "bd:" + directory Entry (DB_DIRECTORY_PREFIX).  Constraint:
// (key≡bucket_directory_record.Directory).
type bucket_directory_record struct {
	Pool      string `json:"pool"`
	Directory string `json:"directory"`
	Timestamp int64  `json:"timestamp"`
}

// "bk:" + bucket Entry (DB_BUCKET_PREFIX).  Constraint:
// (key≡bucket_record.Bucket).
type bucket_record struct {
	Pool            string        `json:"pool"`
	Bucket          string        `json:"bucket"`
	Bucket_policy   bucket_policy `json:"bucket_policy"`
	Expiration_time int64         `json:"expiration_time"`
	Timestamp       int64         `json:"timestamp"`
}

// "sx:" + secret Entry (DB_SECRET_PREFIX).  Constraint:
// (key≡secret_record.Access_key).
type secret_record struct {
	Pool          string        `json:"pool"`
	Access_key    string        `json:"access_key"`
	Secret_key    string        `json:"secret_key"`
	Secret_policy secret_policy `json:"secret_policy"`
	//Internal_use    bool          `json:"internal_use"`
	Expiration_time int64 `json:"expiration_time"`
	Timestamp       int64 `json:"timestamp"`
}

// "mu:" + mux-ep Entry (DB_MUX_EP_PREFIX).  Constraint:
// (key≡mux_record.Mux_ep).
type mux_record struct {
	Mux_ep     string `json:"mux_ep"`
	Start_time int64  `json:"start_time"`
	Timestamp  int64  `json:"timestamp"`
}

// "pt:" + pool-name Entry (DB_POOL_TIMESTAMP_PREFIX).
// type int64

// "us:" + uid Entry (DB_USER_TIMESTAMP_PREFIX).
// type int64

// BUCKET_POLICY is a public-access policy attached to a bucket.  "rw"
// is PUBLIC, "ro" is DOWNLOAD, and "wo" is UPLOAD.
type bucket_policy string

const (
	bucket_policy_RW   bucket_policy = "rw"
	bucket_policy_RO   bucket_policy = "ro"
	bucket_policy_WO   bucket_policy = "wo"
	bucket_policy_NONE bucket_policy = "none"
)

// SECRET_POLICY is a policy attached to an access-key.
type secret_policy string

const (
	secret_policy_RW              secret_policy = "rw"
	secret_policy_RO              secret_policy = "ro"
	secret_policy_WO              secret_policy = "wo"
	secret_policy_internal_access secret_policy = "internal-access"
)

type name_timestamp_pair struct {
	name      string
	timestamp int64
}

type routing_bucket_desc_keys__ struct {
	pool              string
	bucket_policy     string
	modification_time int64
}

// KEY_PAIR is a access-key and a secret-key.
type key_pair struct {
	access_key string
	secret_record
}

// POOL_DIRECTORY is returned by list_buckets_directories()
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
func make_keyval_table(conf *db_conf) *keyval_table {
	var ep = conf.Ep
	var pw = conf.Password

	var setting = redis.NewClient(&redis.Options{
		Addr:     ep,
		Password: pw,
		DB:       setting_db,
	})
	var storage = redis.NewClient(&redis.Options{
		Addr:     ep,
		Password: pw,
		DB:       storage_db,
	})
	var process = redis.NewClient(&redis.Options{
		Addr:     ep,
		Password: pw,
		DB:       process_db,
	})
	var t = &keyval_table{
		ctx:           context.Background(),
		setting:       setting,
		storage:       storage,
		process:       process,
		prefix_to_db:  make(map[string]*redis.Client),
		db_name_to_db: make(map[string]*redis.Client),
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
		var s = t.setting.Ping(t.ctx)
		if s.Err() == nil {
			slogger.Debug("Connected to the keyval-db", "ep", ep)
			return t
		} else {
			slogger.Debug("Connection to a keyval-db failed (sleeping)")
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

func raise_on_set_error(w *redis.StatusCmd) {
	var err = w.Err()
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

func raise_on_setnx_error(w *redis.BoolCmd) {
	var err = w.Err()
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
func raise_on_get_error(w *redis.StringCmd) {
	var err = w.Err()
	if err != nil && err != redis.Nil {
		slogger.Error("db-get() failed", "err", err)
		raise(&proxy_exc{
			"-",
			http_500_internal_server_error,
			[][2]string{
				message_bad_db_entry,
			}})
	}
}

func check_on_del_failure(w *redis.IntCmd) bool {
	var n, err = w.Result()
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

func raise_on_del_failure(w *redis.IntCmd) {
	var n, err = w.Result()
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
func check_on_expire_failure(w *redis.BoolCmd) bool {
	var ok, err = w.Result()
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
	var keyi = scan_table(t, prefix, "*")
	var confs []*lens3_conf
	for keyi.Next(t.ctx) {
		var sub = keyi.Key()
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
	var keyi = scan_table(t, prefix, "*")
	var uu []string
	for keyi.Next(t.ctx) {
		uu = append(uu, keyi.Key())
	}
	return uu
}

func set_user_claim(t *keyval_table, claim string, uid *user_claim_record) {
	db_set_with_prefix(t, db_user_claim_prefix, claim, uid)
}

// GET_CLAIM_USER maps a claim to a uid, or returns il.
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
	var keyi = scan_table(t, prefix, "*")
	for keyi.Next(t.ctx) {
		var k = keyi.Key()
		var claiminguser = get_user_claim(t, k)
		if claiminguser.Uid == uid {
			var k = (prefix + k)
			var w = db.Del(t.ctx, k)
			raise_on_del_failure(w)
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
	var keyi = scan_table(t, prefix, pool)
	var pools []string
	for keyi.Next(t.ctx) {
		pools = append(pools, keyi.Key())
	}
	return pools
}

// SET_EX_BUCKETS_DIRECTORY atomically sets a directory for buckets.
// It returns OK or NG.  On a failure, it returns a current owner in
// the tuple 2nd, as (false,pool).  A returned pool can be "" due to a
// race.
func set_ex_buckets_directory(t *keyval_table, path string, dir *bucket_directory_record) (bool, string) {
	assert_fatal(dir.Directory == path)
	var ok = db_setnx_with_prefix(t, db_directory_prefix, path, dir)
	if ok {
		return true, ""
	}
	// Race, return failure.
	var holder = get_buckets_directory(t, path)
	var holder_pool string
	if holder != nil {
		holder_pool = holder.Pool
	} else {
		holder_pool = ""
	}
	return false, holder_pool
}

func get_buckets_directory(t *keyval_table, path string) *bucket_directory_record {
	var data bucket_directory_record
	var ok = db_get_with_prefix(t, db_directory_prefix, path, &data)
	return ITE(ok, &data, nil)
}

func find_buckets_directory_of_pool(t *keyval_table, pool string) string {
	var prefix = db_directory_prefix
	var keyi = scan_table(t, prefix, "*")
	for keyi.Next(t.ctx) {
		var path = keyi.Key()
		var dir = get_buckets_directory(t, path)
		if dir != nil && dir.Pool == pool {
			return path
		}
	}
	return ""
}

func delete_buckets_directory_unconditionally(t *keyval_table, path string) bool {
	var ok = db_del_with_prefix(t, db_directory_prefix, path)
	return ok
}

// LIST_BUCKETS_DIRECTORIES returns a list of all buckets-directories.
func list_buckets_directories(t *keyval_table) []*bucket_directory_record {
	var prefix = db_directory_prefix
	var keyi = scan_table(t, prefix, "*")
	//var bkts []*pool_directory
	var bkts []*bucket_directory_record
	for keyi.Next(t.ctx) {
		var path = keyi.Key()
		var dir = get_buckets_directory(t, path)
		if dir != nil {
			bkts = append(bkts, dir)
			// bkts = append(bkts, &pool_directory{
			// 	pool:      dir.Pool,
			// 	directory: path,
			// })
		}
	}
	return bkts
}

func set_pool_state(t *keyval_table, pool string, state pool_state, reason pool_reason) {
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

func get_pool_state(t *keyval_table, pool string) *pool_state_record {
	var data pool_state_record
	var ok = db_get_with_prefix(t, db_pool_state_prefix, pool, &data)
	return ITE(ok, &data, nil)
}

func delete_pool_state(t *keyval_table, pool string) {
	db_del_with_prefix(t, db_pool_state_prefix, pool)
}

// SET_EX_MANAGER atomically sets an exclusion for a backend.  It
// returns OK or NG.  It tries to return an old record, but it can be
// null due to a race (but practically never).
func set_ex_backend_exclusion(t *keyval_table, pool string, data *backend_exclusion_record) (bool, *backend_exclusion_record) {
	var ok = db_setnx_with_prefix(t, db_backend_exclusion_prefix, pool, data)
	if ok {
		return true, nil
	}
	// Race, return failure.
	var holder = get_backend_exclusion(t, pool)
	return false, holder
}

func set_backend_exclusion_expiry(t *keyval_table, pool string, timeout int64) bool {
	var ok = db_expire_with_prefix(t, db_backend_exclusion_prefix, pool, timeout)
	return ok
}

func get_backend_exclusion(t *keyval_table, pool string) *backend_exclusion_record {
	var data backend_exclusion_record
	var ok = db_get_with_prefix(t, db_backend_exclusion_prefix, pool, &data)
	return ITE(ok, &data, nil)
}

func delete_backend_exclusion(t *keyval_table, pool string) {
	db_del_with_prefix(t, db_backend_exclusion_prefix, pool)
}

func set_backend(t *keyval_table, pool string, data *backend_record) {
	assert_fatal(data.Pool == pool)
	db_set_with_prefix(t, db_backend_data_prefix, pool, data)
}

func set_backend_expiry(t *keyval_table, pool string, timeout int64) bool {
	var ok = db_expire_with_prefix(t, db_backend_data_prefix, pool, timeout)
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
	var ki = scan_table(t, prefix, pool)
	var procs []*backend_record
	for ki.Next(t.ctx) {
		var id = ki.Key()
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

func set_mux_ep_expiry(t *keyval_table, mux_ep string, timeout int64) bool {
	var ok = db_expire_with_prefix(t, db_mux_ep_prefix, mux_ep, timeout)
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
	var keyi = scan_table(t, prefix, "*")
	var descs []*mux_record
	for keyi.Next(t.ctx) {
		var ep = keyi.Key()
		var d = get_mux_ep(t, ep)
		if d != nil {
			descs = append(descs, d)
		}
	}
	return descs
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

func delete_bucket_unconditionally(t *keyval_table, bucket string) bool {
	var ok = db_del_with_prefix(t, db_bucket_prefix, bucket)
	return ok
}

// LIST_BUCKETS lists buckets.  If pool≠"", lists buckets for a pool.
func list_buckets(t *keyval_table, pool string) []*bucket_record {
	var prefix = db_bucket_prefix
	var keyi = scan_table(t, prefix, "*")
	var descs []*bucket_record
	for keyi.Next(t.ctx) {
		var key = keyi.Key()
		var d = get_bucket(t, key)
		if d == nil {
			continue
		}
		assert_fatal(d.Bucket == key)
		if pool == "" || d.Pool == pool {
			descs = append(descs, d)
		}
	}
	return descs
}

func set_access_timestamp(t *keyval_table, pool string) {
	var now int64 = time.Now().Unix()
	db_set_with_prefix(t, db_pool_timestamp_prefix, pool, now)
}

func get_access_timestamp(t *keyval_table, pool string) int64 {
	var data int64
	var ok = db_get_with_prefix(t, db_pool_timestamp_prefix, pool, &data)
	return ITE(ok, data, 0)
}

func delete_access_timestamp(t *keyval_table, pool string) {
	db_del_with_prefix(t, db_pool_timestamp_prefix, pool)
}

// LIST_ACCESS_TIMESTAMPS returns a list of (pool-id, ts) pairs.
func list_access_timestamps(t *keyval_table) []name_timestamp_pair {
	var prefix = db_pool_timestamp_prefix
	var keyi = scan_table(t, prefix, "*")
	var descs []name_timestamp_pair
	for keyi.Next(t.ctx) {
		var pool = keyi.Key()
		var ts = get_access_timestamp(t, pool)
		if ts == 0 {
			slogger.Info("intenal: list_access_timestamps failed")
			continue
		}
		descs = append(descs, name_timestamp_pair{pool, ts})
	}
	return descs
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
func list_user_timestamps(t *keyval_table) []name_timestamp_pair {
	var prefix = db_user_timestamp_prefix
	var keyi = scan_table(t, prefix, "*")
	var descs []name_timestamp_pair
	for keyi.Next(t.ctx) {
		var uid = keyi.Key()
		var ts = get_user_timestamp(t, uid)
		if ts == 0 {
			slogger.Info("intenal: list_user_timestamps failed")
			continue
		}
		descs = append(descs, name_timestamp_pair{uid, ts})
	}
	return descs
}

// SET_WITH_UNIQUE_POOL_NAME makes a random unique id for a pool-name or an
// access-key.
func set_with_unique_pool_name(t *keyval_table, data *pool_mutex_record) string {
	var prefix = db_pool_name_prefix
	var s = set_with_unique_id_loop(t, prefix, data, generate_random_key)
	return s
}

// SET_WITH_UNIQUE_SECRET_KEY makes a random unique id for a an
// access-key.  The generator function assigns a new access-key in
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
		var v, err = json.Marshal(data)
		raise_on_marshaling_error(err)
		var k = (prefix + id)
		var w = db.SetNX(t.ctx, k, v, db_no_expiration)
		raise_on_setnx_error(w)
		var ok, _ = w.Result()
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

// SET_EX_POOL_MUTEX is used in restoring database.
func set_ex_pool_mutex(t *keyval_table, pool string, data *pool_mutex_record) bool {
	var ok = db_setnx_with_prefix(t, db_pool_name_prefix, pool, data)
	return ok
}

func get_pool_mutex(t *keyval_table, pool string) *pool_mutex_record {
	var data pool_mutex_record
	var ok = db_get_with_prefix(t, db_pool_name_prefix, pool, &data)
	return ITE(ok, &data, nil)
}

func delete_pool_name_unconditionally(t *keyval_table, pool string) bool {
	var ok = db_del_with_prefix(t, db_pool_name_prefix, pool)
	return ok
}

// SET_EX_SECRET is used in restoring database.
func set_ex_secret(t *keyval_table, key string, data *secret_record) bool {
	var ok = db_setnx_with_prefix(t, db_secret_prefix, key, data)
	return ok
}

func get_secret(t *keyval_table, key string) *secret_record {
	var data secret_record
	var ok = db_get_with_prefix(t, db_secret_prefix, key, &data)
	return ITE(ok, &data, nil)
}

// DELETE_SECRET_KEY deletes a access-key, unconditionally.
func delete_secret_key_unconditionally(t *keyval_table, key string) bool {
	var ok = db_del_with_prefix(t, db_secret_prefix, key)
	return ok
}

func delete_secret_key__(t *keyval_table, key string) {
	var prefix = db_secret_prefix
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var w = db.Del(t.ctx, k)
	raise_on_del_failure(w)
}

// LIST_SECRETS_OF_POOL lists secrets (access-keys) of a pool.  It
// includes a probe-key (which is created and used internally).
func list_secrets_of_pool(t *keyval_table, pool string) []*secret_record {
	var prefix = db_secret_prefix
	var keyi = scan_table(t, prefix, "*")
	var accume = []*secret_record{}
	for keyi.Next(t.ctx) {
		var key = keyi.Key()
		var d = get_secret(t, key)
		if d == nil {
			// Race.  It is not an error.
			continue
		}
		if d.Pool != pool {
			continue
		}
		// d.Access_key = key
		accume = append(accume, d)
	}
	return accume
}

func set_csrf_token(t *keyval_table, uid string, token *csrf_token_record) {
	db_set_with_prefix(t, db_csrf_token_prefix, uid, token)
}

func set_csrf_token_expiry(t *keyval_table, uid string, timeout int64) bool {
	var ok = db_expire_with_prefix(t, db_csrf_token_prefix, uid, timeout)
	return ok
}

func get_csrf_token(t *keyval_table, uid string) *csrf_token_record {
	var data csrf_token_record
	var ok = db_get_with_prefix(t, db_csrf_token_prefix, uid, &data)
	return ITE(ok, &data, nil)
}

func db_set_with_prefix(t *keyval_table, prefix string, key string, val any) {
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var v, err = json.Marshal(val)
	raise_on_marshaling_error(err)
	var w = db.Set(t.ctx, k, v, db_no_expiration)
	raise_on_set_error(w)
}

func db_setnx_with_prefix(t *keyval_table, prefix string, key string, val any) bool {
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var v, err = json.Marshal(val)
	raise_on_marshaling_error(err)
	var w = db.SetNX(t.ctx, k, v, db_no_expiration)
	raise_on_setnx_error(w)
	var ok, _ = w.Result()
	return ok
}

func db_get_with_prefix(t *keyval_table, prefix string, key string, val any) bool {
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var w = db.Get(t.ctx, k)
	raise_on_get_error(w)
	var ok = load_db_data(w, val)
	return ok
}

func db_expire_with_prefix(t *keyval_table, prefix string, key string, timeout int64) bool {
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var w = db.Expire(t.ctx, k, (time.Duration(timeout) * time.Second))
	var ok = check_on_expire_failure(w)
	return ok
}

// DB_DEL_WITH_PREFIX returns OK/NG, but usually, failure is ignored.
func db_del_with_prefix(t *keyval_table, prefix string, key string) bool {
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var w = db.Del(t.ctx, k)
	var ok = check_on_del_failure(w)
	return ok
}

// DB_DEL_WITH_PREFIX raises, when delete failed.
func db_del_with_prefix_raise(t *keyval_table, prefix string, key string) {
	var db = t.prefix_to_db[prefix]
	var k = (prefix + key)
	var w = db.Del(t.ctx, k)
	raise_on_del_failure(w)
}

// LOAD_DATA fills a structure by json data in the keyval-db.  It
// returns true or false about an entry is found.  Note that a get
// with err=redis.Nil means a non-exising entry.
func load_db_data(w *redis.StringCmd, data any) bool {
	var b, err1 = w.Bytes()
	if err1 != nil {
		if err1 == redis.Nil {
			return false
		} else {
			slogger.Error("Bad value in the keyval-db", "err", err1)
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

// SCAN_TABLE returns an iterator of keys for a prefix+target pattern,
// where a target is "*" for a wildcard.  It drops the prefix from the
// returned keys.  Note that a null-ness check is always necessary
// when getting a value, because a deletion can intervene scanning
// keys and getting values.
func scan_table(t *keyval_table, prefix string, target string) *db_key_iterator {
	var db = t.prefix_to_db[prefix]
	var pattern = prefix + target
	var prefix_length = len(prefix)
	var ki = db_key_iterator{
		prefix_length,
		db.Scan(t.ctx, 0, pattern, 0).Iterator(),
	}
	return &ki
}

// DB_KEY_ITERATOR is a scanner, also containing a length of a
// key-prefix.  It removes a key-prefix from a key while iterating.
type db_key_iterator struct {
	prefix_length int
	i             *redis.ScanIterator
}

func (keyi *db_key_iterator) Err() error {
	return keyi.i.Err()
}

func (keyi *db_key_iterator) Next(ctx context.Context) bool {
	return keyi.i.Next(ctx)
}

func (keyi *db_key_iterator) Key() string {
	//CHECK-STRING-LENGTH
	var k = keyi.i.Val()
	return k[keyi.prefix_length:]
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

func clear_db(t *keyval_table, db *redis.Client, prefix string) {
	assert_fatal(len(prefix) == 3)
	var pattern = (prefix + "*")
	var keyi = db.Scan(t.ctx, 0, pattern, 0).Iterator()
	for keyi.Next(t.ctx) {
		var k = keyi.Val()
		var _ = db.Del(t.ctx, k)
		//raise_when_db_fail(w.Err())
	}
}

// DB_RAW_TABLE returns a keyval-db for a db-name: {"setting",
// "storage", "process"}.
func db_raw_table(t *keyval_table, name string) *redis.Client {
	var db, ok = t.db_name_to_db[name]
	if !ok {
		slogger.Error("Bad keybal-db name", "name", name)
		return nil
	}
	return db
}

// SET_DB_RAW sets key-value in the keyval-db intact.
func set_db_raw(t *keyval_table, kv [2]string) {
	if kv[0] == "" || kv[1] == "" {
		slogger.Error("Empty keyval to the keybal-db", "kv", kv)
		panic(nil)
	}
	var prefix = kv[0][:3]
	var db = t.prefix_to_db[prefix]
	if db == nil {
		slogger.Error("Bad prefix to the keybal-db", "prefix", prefix)
		panic(nil)
	}
	var w = db.Set(t.ctx, kv[0], kv[1], db_no_expiration)
	raise_on_set_error(w)
}

func adm_del_db_raw(t *keyval_table, key string) {
	if key == "" {
		slogger.Error("Empty key to the keybal-db")
		panic(nil)
	}
	//var prefix = key[:3]
	//var db = t.prefix_to_db[prefix]
	//if db != nil {
	//	var w *redis.IntCmd = db.Del(t.ctx, key)
	//	raise_when_db_fail(w.Err())
	//}
	for name, db := range t.db_name_to_db {
		var w *redis.IntCmd = db.Del(t.ctx, key)
		var n, err = w.Result()
		if err == nil && n == 1 {
			fmt.Printf("deleted (%s) in the keyval-db\n", name)
		}
	}
}

type db_raw_iterator struct {
	table    *keyval_table
	db       *redis.Client
	iterator *redis.ScanIterator
}

// SCAN_DB_RAW returns a (raw) iterator of the keyval-db.  It returns
// nil for a bad db name.
func scan_db_raw(t *keyval_table, dbname string) *db_raw_iterator {
	var db = db_raw_table(t, dbname)
	if db == nil {
		return nil
	}
	return &db_raw_iterator{
		table:    t,
		db:       db,
		iterator: db.Scan(t.ctx, 0, "*", 0).Iterator(),
	}
}

// NEXT_DB_RAW returns a next entry of the iterator.  It returns a map
// with a single entry, or returns nil at the end.  A value part is a
// json string.
func next_db_raw(db *db_raw_iterator) map[string]string {
	for db.iterator.Next(db.table.ctx) {
		var key = db.iterator.Val()
		var w = db.db.Get(db.table.ctx, key)
		var val, err1 = w.Bytes()
		if err1 != nil {
			// w.Err() case subsumed.
			if err1 == redis.Nil {
				continue
			} else {
				slogger.Error("Get in the keybal-db failed", "err", err1)
				panic(nil)
			}
		}
		return map[string]string{key: string(val)}
	}
	return nil
}
