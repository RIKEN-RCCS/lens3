/* Accessors to a Keyval-DB (Redis/Valkey). */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// A table is accessed like a single database, while consists of a set
// of five databases to easy manual inspection in the keyval-db.

import (
	// This is by "go-redis/v8".  Use "go-redis/v8" for Redis-6, or
	// "go-redis/v9" for Redis-7.

	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"github.com/go-redis/redis/v8"
	"log"
	"time"
	//"reflect"
)

const limit_of_id_generation_loop = 30

type keyval_table struct {
	ctx              context.Context
	setting          *redis.Client
	storage          *redis.Client
	process          *redis.Client
	key_prefix_to_db map[string]*redis.Client
}

// Configuration entries are defined in "conf.go".  They are "cf:api",
// "cf:mux", and "cf:mux":mux-name .

// "uu:uid" entry.
type user_record struct {
	Uid             string   `json:"uid"`
	Claim           string   `json:"claim"`
	Groups          []string `json:"groups"`
	Enabled         bool     `json:"enabled"`
	Blocked         bool     `json:"blocked"`         // nonexist
	Expiration_time int64    `json:"expiration_time"` // nonexist

	Check_terms_and_conditions bool  `json:"check_terms_and_conditions"`
	Modification_time          int64 `json:"modification_time"`
}

// "po:pool-name" entry.
type pool_record struct {
	Pool              string `json:"pool_name"`
	Buckets_directory string `json:"buckets_directory"`
	Owner_uid         string `json:"owner_uid"`
	Owner_gid         string `json:"owner_gid"`
	Probe_key         string `json:"probe_key"`
	Online_status     bool   `json:"online_status"`
	Expiration_time   int64  `json:"expiration_time"`

	Modification_time int64 `json:"modification_time"`
}

// "bk:bucket-name" entry.
type bucket_record struct {
	bucket          string `json:"-"`
	Pool            string `json:"pool"`
	Bkt_policy      string `json:"bkt_policy"`
	Expiration_time int64  `json:"expiration_time"` // nonexist

	Modification_time int64 `json:"modification_time"`
}

// "ky:random" entry.  The access_key field is not stored in a
// keyval-db.  (v1.2 "owner" → v2.1 "pool").
type secret_record struct {
	Pool            string `json:"pool"`
	access_key      string `json:"-"`
	Secret_key      string `json:"secret_key"`
	Key_policy      string `json:"key_policy"`
	Expiration_time int64  `json:"expiration_time"`

	Modification_time int64 `json:"modification_time"`
}

// "um:claim" entry is a string.
type user_claim_record string

// "pi:pool-name" entry.
type Pool_name_record struct {
	Owner_uid string `json:"owner"`

	Modification_time int64 `json:"modification_time"`
}

// "bd:directory" entry is a string.
type directory_owner_record string

// "ep:pool-name" entry is a string.
type backend_ep_record string

// "bx:pool-name" entry.
type manager_record struct {
	Mux_ep     string `json:"mux_ep"` // mux_host:mux_port
	Start_time int64  `json:"start_time"`
}

// "ps:pool-name" entry.
type pool_state_record struct {
	State  pool_state  `json:"state"`
	Reason pool_reason `json:"reason"`

	Modification_time int64 `json:"modification_time"`
}

// "be:pool-name" entry.  BACKEND_RECORD is about a backend.  A pair
// of root_access and root_secret is a credential for accessing a
// backend.  manager_pid is unused.
type backend_record struct {
	Backend_ep  string `json:"backend_ep"`  // Minio_ep
	Backend_pid int    `json:"backend_pid"` // Minio_pid
	Root_access string `json:"root_access"` // Admin
	Root_secret string `json:"root_secret"` // Password
	Mux_ep      string `json:"mux_ep"`      // Mux_host+Mux_port
	Mux_pid     int    `json:"mux_pid"`     // Manager_pid

	Modification_time int64 `json:"modification_time"`
}

// "mu:mux-ep" entry.
type Mux_record struct {
	Mux_ep     string `json:"mux_ep"` // Host+Port
	Start_time int64  `json:"start_time"`

	Modification_time int64 `json:"modification_time"`
}

// "ts:pool-name" entry is an int64
type pool_access_timestamp_record int64

// "us:uid" entry is an int64
type user_access_timestamp_record int64

// KEY_POLICY is a policy attached to an access-key.
type key_policy string

const (
	key_policy_READWRITE key_policy = "readwrite"
	key_policy_READONLY  key_policy = "readonly"
	key_policy_WRITEONLY key_policy = "writeonly"
)

// BKT_POLICY is a public-access policy attached to a bucket.
type bkt_policy string

const (
	bkt_policy_NONE     bkt_policy = "none"
	bkt_policy_UPLOAD   bkt_policy = "upload"
	bkt_policy_DOWNLOAD bkt_policy = "download"
	bkt_policy_PUBLIC   bkt_policy = "public"
)

// XID_RECORD is a union of Pool_name_record|secret_record.
type xid_record interface{ xid_union() }

func (Pool_name_record) xid_union() {}
func (secret_record) xid_union()    {}

type name_timestamp_pair struct {
	name      string
	timestamp int64
}

type routing_bucket_desc_keys__ struct {
	pool              string
	bkt_policy        string
	modification_time int64
}

// KEY_PAIR is a access-key and a secret-key.
type key_pair struct {
	access_key string
	secret_record
}

// POOL_DIRECTORY is returned by list_buckets_directories()
type pool_directory struct {
	pool      string
	directory string
}

// Enum of random-key usage.
type key_usage string

const (
	key_usage_pool key_usage = "pool"
	key_usage_akey key_usage = "akey"
)

// DB numbers.
const setting_db = 1
const storage_db = 2
const process_db = 3

var db_name_to_number = map[string]int{
	"setting": 1,
	"storage": 2,
	"process": 3,
}

const (
	db_conf_prefix       = "cf:"
	db_user_info_prefix  = "uu:"
	db_user_claim_prefix = "um:"

	db_pool_data_prefix         = "po:"
	db_buckets_directory_prefix = "bd:"
	db_pool_name_prefix         = "pk:"
	db_secret_prefix            = "sk:" // ky -> si
	db_bucket_prefix            = "bk:"

	db_mux_ep_prefix          = "mu:" // mx -> mu
	db_backend_manager_prefix = "bx:" // ma -> bx
	db_backend_process_prefix = "be:"
	//db_backend_ep_prefix       = "ep:"
	db_pool_state_prefix       = "ps:"
	db_access_timestamp_prefix = "ts:"
	db_user_timestamp_prefix   = "us:"
)

var key_prefix_to_db_number = map[string]int{
	db_conf_prefix:       setting_db,
	db_user_info_prefix:  setting_db,
	db_user_claim_prefix: setting_db,

	db_pool_data_prefix:         storage_db,
	db_buckets_directory_prefix: storage_db,
	db_pool_name_prefix:         storage_db,
	db_secret_prefix:            storage_db,
	db_bucket_prefix:            storage_db,

	db_mux_ep_prefix:          process_db,
	db_backend_manager_prefix: process_db,
	db_backend_process_prefix: process_db,
	//db_backend_ep_prefix:       process_db,
	db_pool_state_prefix:       process_db,
	db_access_timestamp_prefix: process_db,
	db_user_timestamp_prefix:   process_db,
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
// be appended to another reason.
type pool_reason string

const (
	// pool_state_INITIAL or pool_state_READY.
	pool_reason_NORMAL pool_reason = "-"

	// pool_state_SUSPENDED.
	pool_reason_BACKEND_BUSY pool_reason = "backend busy"

	// pool_state_DISABLED.
	pool_reason_POOL_EXPIRED  pool_reason = "pool expired"
	pool_reason_USER_DISABLED pool_reason = "user disabled"
	pool_reason_POOL_OFFLINE  pool_reason = "pool offline"

	// pool_state_INOPERABLE.
	pool_reason_POOL_REMOVED pool_reason = "pool removed"
	pool_reason_USER_REMOVED pool_reason = "user removed"
	pool_reason_EXEC_FAILED  pool_reason = "start failed: "
	pool_reason_SETUP_FAILED pool_reason = "initialization failed: "

	// Other reasons are exceptions and messages from a backend.

	pool_reason_POOL_DISABLED_INITIALLY_ pool_reason = "pool disabled initially"
)

// MAKE_TABLE makes keyval-db clients.
func make_table(conf db_conf) *keyval_table {
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
		ctx:              context.Background(),
		setting:          setting,
		storage:          storage,
		process:          process,
		key_prefix_to_db: make(map[string]*redis.Client),
	}
	for k, i := range key_prefix_to_db_number {
		switch i {
		case setting_db:
			t.key_prefix_to_db[k] = setting
		case storage_db:
			t.key_prefix_to_db[k] = storage
		case process_db:
			t.key_prefix_to_db[k] = process
		default:
			panic("internal")
		}
	}

	// Wait for a keyval-db.

	for {
		var s = t.setting.Ping(t.ctx)
		if s.Err() == nil {
			log.Print("Connected to a keyval-db.")
			return t
		} else {
			log.Print("Connection to a keyval-db failed (sleeping).")
			time.Sleep(30 * time.Second)
		}
	}
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

// SCAN_TABLE returns an iterator of keys for a prefix+target pattern,
// where a target is "*" for a wildcard.  It drops the prefix from the
// returned keys.  Note a null-ness check is always necessary when
// getting a value, because a deletion can intervene scanning keys and
// getting values.
func scan_table(t *keyval_table, prefix string, target string) *db_key_iterator {
	var db = t.key_prefix_to_db[prefix]
	var pattern = prefix + target
	var prefix_length = len(prefix)
	var ki = db_key_iterator{
		prefix_length,
		db.Scan(t.ctx, 0, pattern, 0).Iterator()}
	return &ki
}

// LOAD_DATA fills a structure by json data in a keyval-db.  It
// returns true or false if no entry is found.
func load_db_data(v *redis.StringCmd, data any) bool {
	var b, err1 = v.Bytes()
	if err1 != nil {
		if err1 == redis.Nil {
			return false
		} else {
			panic(err1)
		}
	}

	// Old db stores strings without quotes (not in json).  Handle
	// them specically.

	if false {
		switch s := data.(type) {
		case *string:
			*s = string(b)
			return true
		}
	}

	var r = bytes.NewReader(b)
	var d = json.NewDecoder(r)
	d.DisallowUnknownFields()
	var err2 = d.Decode(data)
	if err2 != nil {
		//fmt.Println("d=", string(b))
		log.Panic("Bad json data in a keyval-db: ", err2)
	}
	return true
}

func load_db_data__(v *redis.StringCmd, data any) bool {
	var b, err1 = v.Bytes()
	if err1 != nil {
		if err1 == redis.Nil {
			return false
		} else {
			panic(err1)
		}
	}
	var err2 = json.Unmarshal(b, data)
	if err2 != nil {
		panic(fmt.Sprint("Bad json data in a keyval-db", err1))
	}
	return true
}

/* SETTING-TABLE */

func set_conf(t *keyval_table, conf lens3_conf) {
	var prefix = db_conf_prefix
	var db = t.key_prefix_to_db[prefix]
	//var ctx = context.Background()
	switch conf1 := conf.(type) {
	case *mux_conf:
		var sub = conf1.Subject
		if !(sub == "mux" || (len(sub) >= 5 && sub[:4] == "mux:")) {
			panic("bad conf; subject≠mux")
		}
		var k1 = (db_conf_prefix + sub)
		var v1, err1 = json.Marshal(conf1)
		if err1 != nil {
			panic(err1)
		}
		// Zero for no expiration.
		var w1 = db.Set(t.ctx, k1, v1, 0)
		panic_non_nil(w1.Err())
	case *api_conf:
		var sub = conf1.Subject
		if !(sub == "api") {
			panic("bad conf; subject≠api")
		}
		var k2 = (db_conf_prefix + sub)
		var v2, err1 = json.Marshal(conf1)
		if err1 != nil {
			panic(err1)
		}
		var w2 = db.Set(t.ctx, k2, v2, 0)
		panic_non_nil(w2.Err())
	default:
		log.Panicf("type: (%T) type≠mux_conf nor type≠api_conf\n", conf)
	}
}

func delete_conf(t *keyval_table, sub string) {
	var prefix = db_conf_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + sub)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_CONFS returns a list of confs.  It contains both mux_conf and
// api_conf.
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
		case sub == "api":
			v = get_api_conf(t, sub)
		default:
			panic(fmt.Sprint("Bad subject name"))
		}
		if v != nil {
			confs = append(confs, &v)
		}
	}
	return confs
}

func get_mux_conf(t *keyval_table, sub string) *mux_conf {
	var prefix = db_conf_prefix
	var db = t.key_prefix_to_db[prefix]
	assert_fatal(sub == "mux" || (len(sub) >= 5 && sub[:4] == "mux:"))
	var k = (prefix + sub)
	var w = db.Get(t.ctx, k)
	var conf mux_conf
	var ok = load_db_data(w, &conf)
	if ok {
		//fmt.Println("MUX CONF is", conf)
		check_mux_conf(&conf)
		return &conf
	} else {
		return nil
	}
}

func get_api_conf(t *keyval_table, sub string) *api_conf {
	assert_fatal(sub == "api")
	var prefix = db_conf_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + sub)
	var w = db.Get(t.ctx, k)
	var conf api_conf
	var ok = load_db_data(w, &conf)
	if ok {
		//fmt.Println("API CONF is", conf)
		check_api_conf(&conf)
		return &conf
	} else {
		return nil
	}
}

// ADD_USER adds a user and its claim entry.  A duplicate claim is an
// error.  It deletes an old entry first if exits.
func add_user(t *keyval_table, ui *user_record) {
	var uid = ui.Uid
	var claim = ui.Claim
	assert_fatal(uid != "")
	assert_fatal(len(ui.Groups) > 0)
	if claim != "" {
		var claiminguser = get_claim_user(t, claim)
		if uid != *claiminguser {
			var err2 = fmt.Errorf("A claim for {uid} conflicts with {xid}")
			panic(err2)
		}
	}
	delete_user(t, uid)
	set_user_force(t, ui)
}

// (Use add_user() instead).
func set_user_force(t *keyval_table, ui *user_record) {
	var prefix = db_user_info_prefix
	var db = t.key_prefix_to_db[prefix]
	var uid = ui.Uid
	assert_fatal(uid != "")
	var v, err1 = json.Marshal(&ui)
	if err1 != nil {
		panic(err1)
	}
	var k1 = (prefix + uid)
	var w1 = db.Set(t.ctx, k1, v, 0)
	panic_non_nil(w1.Err())
	var claim = ui.Claim
	if claim != "" {
		set_user_claim(t, claim, ui.Uid)
		var k2 = (prefix + claim)
		var w2 = db.Set(t.ctx, k2, v, 0)
		panic_non_nil(w2.Err())
	}
}

// GET_USER gets a user by a uid.  It may return nil.
func get_user(t *keyval_table, uid string) *user_record {
	var prefix = db_user_info_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + uid)
	var w = db.Get(t.ctx, k)
	var ui user_record
	var ok = load_db_data(w, &ui)
	if ok {
		return &ui
	} else {
		return nil
	}
}

// DELETE_USER deletes a user and its associated claim entry.
func delete_user(t *keyval_table, uid string) {
	var prefix = db_user_info_prefix
	var db = t.key_prefix_to_db[prefix]
	var ui = get_user(t, uid)
	if ui == nil {
		return
	}
	var k = (prefix + uid)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
	var claim = ui.Claim
	if claim != "" {
		delete_user_claim(t, claim)
		clear_user_claim(t, uid)
	}
}

// LIST_USERS lists all uid's.
func list_users(t *keyval_table) []string {
	var prefix = db_user_info_prefix
	var keyi = scan_table(t, prefix, "*")
	var uu []string
	for keyi.Next(t.ctx) {
		uu = append(uu, keyi.Key())
	}
	return uu
}

func set_user_claim(t *keyval_table, claim string, uid string) {
	var prefix = db_user_claim_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + claim)
	var v, err = json.Marshal(uid)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

// GET_CLAIM_USER maps a claim to a uid, or returns il.
func get_claim_user(t *keyval_table, claim string) *string {
	assert_fatal(claim != "")
	var prefix = db_user_claim_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + claim)
	var w = db.Get(t.ctx, k)
	var uid string
	var ok = load_db_data(w, &uid)
	if ok {
		return &uid
	} else {
		return nil
	}
}

func delete_user_claim(t *keyval_table, claim string) {
	var prefix = db_user_claim_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + claim)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// CLEAR_USER_CLAIM deletes a claim associated to an uid.  It scans
// all the claims.  (This is paranoiac because it is called after
// deleting a claim entry).
func clear_user_claim(t *keyval_table, uid string) {
	var prefix = db_user_claim_prefix
	var db = t.key_prefix_to_db[prefix]
	var keyi = scan_table(t, prefix, "*")
	for keyi.Next(t.ctx) {
		var k = keyi.Key()
		var claiminguser = get_claim_user(t, k)
		if uid == *claiminguser {
			var k = (prefix + k)
			var w = db.Del(t.ctx, k)
			panic_non_nil(w.Err())
		}
	}
}

/* STORAGE-TABLE */

func set_pool(t *keyval_table, pool string, desc *pool_record) {
	var prefix = db_pool_data_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func get_pool(t *keyval_table, pool string) *pool_record {
	var prefix = db_pool_data_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Get(t.ctx, k)
	var desc pool_record
	var ok = load_db_data(w, &desc)
	if ok {
		return &desc
	} else {
		return nil
	}
}

func delete_pool(t *keyval_table, pool string) {
	var prefix = db_pool_data_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
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
// At a failure, it returns a current owner, that is,
// (false,owner-uid).  A returned owner could be nil due to a race.
func set_ex_buckets_directory(t *keyval_table, path string, pool string) (bool, string) {
	var prefix = db_buckets_directory_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + path)
	var w = db.SetNX(t.ctx, k, pool, 0)
	if w.Err() == nil {
		return true, ""
	}
	var o = get_buckets_directory(t, path)
	// An ower may be nil by a possible race; it is ignored.
	return false, o
}

func get_buckets_directory(t *keyval_table, path string) string {
	var prefix = db_buckets_directory_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + path)
	var w = db.Get(t.ctx, k)
	var dir string
	var ok = load_db_data(w, &dir)
	if ok {
		return dir
	} else {
		return ""
	}
}

func get_buckets_directory_of_pool(t *keyval_table, pool string) string {
	var prefix = db_buckets_directory_prefix
	var keyi = scan_table(t, prefix, "*")
	for keyi.Next(t.ctx) {
		var path = keyi.Key()
		var ownerpool = get_buckets_directory(t, path)
		if ownerpool != "" && ownerpool == pool {
			return path
		}
	}
	return ""
}

func delete_buckets_directory(t *keyval_table, path string) {
	var prefix = db_buckets_directory_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + path)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_BUCKETS_DIRECTORIES returns a list of all buckets-directories.
func list_buckets_directories(t *keyval_table) []*pool_directory {
	var prefix = db_buckets_directory_prefix
	var keyi = scan_table(t, prefix, "*")
	var bkts []*pool_directory
	for keyi.Next(t.ctx) {
		var path = keyi.Key()
		var pool = get_buckets_directory(t, path)
		if pool != "" {
			bkts = append(bkts, &pool_directory{
				pool:      pool,
				directory: path,
			})
		}
	}
	return bkts
}

func set_pool_state(t *keyval_table, pool string, state pool_state, reason pool_reason) {
	var prefix = db_pool_state_prefix
	var db = t.key_prefix_to_db[prefix]
	var now int64 = time.Now().Unix()
	var record = pool_state_record{
		State:             state,
		Reason:            reason,
		Modification_time: now,
	}
	var k = (prefix + pool)
	var v, err = json.Marshal(record)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func get_pool_state(t *keyval_table, pool string) *pool_state_record {
	var prefix = db_pool_state_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Get(t.ctx, k)
	var state pool_state_record
	var ok = load_db_data(w, &state)
	if ok {
		return &state
	} else {
		return nil
	}
}

func delete_pool_state(t *keyval_table, pool string) {
	var prefix = db_pool_state_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

/* PROCESS-TABLE */

// SET_EX_MANAGER_LOCK atomically sets a manager record that is used
// as a mutex.  It returns OK/NG.  It returns an old record, but it
// can be null due to a race (but practically never).
func set_ex_manager_lock(t *keyval_table, pool string, desc *manager_record) (bool, *manager_record) {
	var prefix = db_backend_manager_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = db.SetNX(t.ctx, k, v, 0)
	if w.Err() == nil {
		return true, nil
	} else {
		// Race, returns failure.
		var o = get_manager(t, pool)
		return false, o
	}
}

func set_manager_expiry(t *keyval_table, pool string, timeout int64) {
	var prefix = db_backend_manager_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Expire(t.ctx, k, (time.Duration(timeout) * time.Second))
	panic_non_nil(w.Err())
}

func get_manager(t *keyval_table, pool string) *manager_record {
	var prefix = db_backend_manager_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Get(t.ctx, k)
	var ep manager_record
	var ok = load_db_data(w, &ep)
	if ok {
		return &ep
	} else {
		return nil
	}
}

func delete_manager(t *keyval_table, pool string) {
	var prefix = db_backend_manager_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

func set_backend_process(t *keyval_table, pool string, desc *backend_record) {
	var prefix = db_backend_process_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func get_backend_process(t *keyval_table, pool string) *backend_record {
	var prefix = db_backend_process_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Get(t.ctx, k)
	var proc backend_record
	var ok = load_db_data(w, &proc)
	if ok {
		return &proc
	} else {
		return nil
	}
}

func delete_backend_process(t *keyval_table, pool string) {
	var prefix = db_backend_process_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_BACKEND_PROCESSESS returns a list of all currently running
// servers.
func list_backend_processes(t *keyval_table, pool string) []*backend_record {
	var prefix = db_backend_process_prefix
	var ki = scan_table(t, prefix, pool)
	var procs []*backend_record
	for ki.Next(t.ctx) {
		var id = ki.Key()
		var p = get_backend_process(t, id)
		if p != nil {
			procs = append(procs, p)
		}
	}
	return procs
}

func set_mux_ep(t *keyval_table, mux_ep string, desc *Mux_record) {
	var prefix = db_mux_ep_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + mux_ep)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func set_mux_ep_expiry(t *keyval_table, mux_ep string, timeout int64) {
	var prefix = db_mux_ep_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + mux_ep)
	var w = db.Expire(t.ctx, k, (time.Duration(timeout) * time.Second))
	panic_non_nil(w.Err())
}

func get_mux_ep(t *keyval_table, mux_ep string) *Mux_record {
	var prefix = db_mux_ep_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + mux_ep)
	var w = db.Get(t.ctx, k)
	var desc Mux_record
	var ok = load_db_data(w, &desc)
	if ok {
		return &desc
	} else {
		return nil
	}
}

func delete_mux_ep(t *keyval_table, mux_ep string) {
	var prefix = db_mux_ep_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + mux_ep)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_MUX_EPS returns a list of Mux-record.
func list_mux_eps(t *keyval_table) []*Mux_record {
	var prefix = db_mux_ep_prefix
	var keyi = scan_table(t, prefix, "*")
	var descs []*Mux_record
	for keyi.Next(t.ctx) {
		var ep = keyi.Key()
		var d = get_mux_ep(t, ep)
		if d != nil {
			descs = append(descs, d)
		}
	}
	return descs
}

/* ROUTING-TABLE */

// SET_EX_BUCKET atomically registers a bucket.  It returns OK/NG,
// paired with a pool-id that took the bucket name earlier when it
// fails.  At a failure, a returned current owner information can be
// None due to a race (but practically never).
func set_ex_bucket(t *keyval_table, bucket string, desc bucket_record) (string, bool) {
	var prefix = db_bucket_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + bucket)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = db.SetNX(t.ctx, k, v, 0)
	if w.Err() == nil {
		return "", true
	} else {
		// Race, returns failure.
		var o = get_bucket(t, bucket)
		return o.Pool, false
	}
}

func get_bucket(t *keyval_table, bucket string) *bucket_record {
	var prefix = db_bucket_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + bucket)
	var w = db.Get(t.ctx, k)
	var desc bucket_record
	var ok = load_db_data(w, &desc)
	if ok {
		desc.bucket = bucket
		return &desc
	} else {
		return nil
	}
}

func delete_bucket(t *keyval_table, bucket string) {
	var prefix = db_bucket_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + bucket)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_BUCKETS lists buckets.  If pool≠"", lists buckets for a pool.
func list_buckets(t *keyval_table, pool string) map[string]*bucket_record {
	var prefix = db_bucket_prefix
	var keyi = scan_table(t, prefix, "*")
	var descs = map[string]*bucket_record{}
	for keyi.Next(t.ctx) {
		var key = keyi.Key()
		var d = get_bucket(t, key)
		if d == nil {
			continue
		}
		if pool == "" || d.Pool == pool {
			//descs = append(descs, d)
			descs[key] = d
		}
	}
	return descs
}

/*
func set_backend_ep(t *keyval_table, pool string, ep string) {
	var prefix = db_backend_ep_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var v, err = json.Marshal(ep)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func get_backend_ep(t *keyval_table, pool string) string {
	var prefix = db_backend_ep_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Get(t.ctx, k)
	var desc string
	var ok = load_db_data(w, &desc)
	if ok {
		return desc
	} else {
		return ""
	}
}

func delete_backend_ep(t *keyval_table, pool string) {
	var prefix = db_backend_ep_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

func list_backend_eps(t *keyval_table) []string {
	var prefix = db_backend_ep_prefix
	var keyi = scan_table(t, prefix, "*")
	var descs []string
	for keyi.Next(t.ctx) {
		var ep = keyi.Key()
		var d = get_backend_ep(t, ep)
		if d != "" {
			descs = append(descs, d)
		}
	}
	return descs
}
*/

func set_access_timestamp(t *keyval_table, pool string) {
	var prefix = db_access_timestamp_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var now int64 = time.Now().Unix()
	var v, err = json.Marshal(now)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func get_access_timestamp(t *keyval_table, pool string) int64 {
	var prefix = db_access_timestamp_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Get(t.ctx, k)
	var desc int64
	var ok = load_db_data(w, &desc)
	if ok {
		return desc
	} else {
		return 0
	}
}

func delete_access_timestamp(t *keyval_table, pool string) {
	var prefix = db_access_timestamp_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_ACCESS_TIMESTAMPS returns a list of (pool-id, ts) pairs.
func list_access_timestamps(t *keyval_table) []name_timestamp_pair {
	var prefix = db_access_timestamp_prefix
	var keyi = scan_table(t, prefix, "*")
	var descs []name_timestamp_pair
	for keyi.Next(t.ctx) {
		var pool = keyi.Key()
		var ts = get_access_timestamp(t, pool)
		if ts == 0 {
			logger.infof("intenal: list_access_timestamps")
		}
		descs = append(descs, name_timestamp_pair{pool, ts})
	}
	return descs
}

func set_user_timestamp(t *keyval_table, uid string) {
	var prefix = db_user_timestamp_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + uid)
	var now int64 = time.Now().Unix()
	var v, err = json.Marshal(now)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

// It returns 0 on an internal db-access error.
func get_user_timestamp(t *keyval_table, uid string) int64 {
	var prefix = db_user_timestamp_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + uid)
	var w = db.Get(t.ctx, k)
	var desc int64
	var ok = load_db_data(w, &desc)
	if ok {
		return desc
	} else {
		return 0
	}
}

func delete_user_timestamp(t *keyval_table, uid string) {
	var prefix = db_user_timestamp_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + uid)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
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
			logger.infof("intenal: List_user_timestamps")
		}
		descs = append(descs, name_timestamp_pair{uid, ts})
	}
	return descs
}

/* MONOKEY-TABLE */

func choose_prefix_by_usage(usage key_usage) (string, xid_record) {
	switch usage {
	case key_usage_pool:
		var desc Pool_name_record
		return db_pool_name_prefix, &desc
	case key_usage_akey:
		var desc secret_record
		return db_secret_prefix, &desc
	default:
		logger.error("internal")
		return "", nil
	}
}

// MAKE_UNIQUE_ID makes a random unique id for a pool-name or an
// access-key.
func make_unique_id(t *keyval_table, usage key_usage, owner string, info xid_record) string {
	var prefix, _ = choose_prefix_by_usage(usage)
	var db = t.key_prefix_to_db[prefix]
	var now int64 = time.Now().Unix()
	var v []byte
	var err error
	switch desc := info.(type) {
	case Pool_name_record:
		assert_fatal(usage == key_usage_pool)
		desc.Owner_uid = owner
		desc.Modification_time = now
		v, err = json.Marshal(desc)
		panic_non_nil(err)
	case secret_record:
		assert_fatal(usage == key_usage_akey)
		desc.Pool = owner
		desc.Modification_time = now
		v, err = json.Marshal(desc)
		panic_non_nil(err)
	default:
		panic("internal")
	}
	var xid_generation_loops = 0
	for {
		var xid string
		switch info.(type) {
		case Pool_name_record:
			xid = generate_pool_name()
		case secret_record:
			xid = generate_access_key()
		default:
			panic("internal")
		}
		var k = (prefix + xid)
		var w = db.SetNX(t.ctx, k, v, 0)
		if w.Err() == nil {
			return xid
		}
		// Retry.
		xid_generation_loops += 1
		if !(xid_generation_loops < limit_of_id_generation_loop) {
			panic("internal: unique key generation")
		}
	}
}

// SET_EX_POOL_NAME is used in restoring database.
func set_ex_pool_name(t *keyval_table, pool string, desc *Pool_name_record) bool {
	var prefix = db_pool_name_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = db.SetNX(t.ctx, k, v, 0)
	if w.Err() != nil {
		return false
	} else {
		return true
	}
}

func get_pool_name(t *keyval_table, pool string) *Pool_name_record {
	var prefix = db_pool_name_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Get(t.ctx, k)
	var desc Pool_name_record
	var ok = load_db_data(w, &desc)
	if ok {
		return &desc
	} else {
		return nil
	}
}

func delete_pool_name_unconditionally(t *keyval_table, pool string) {
	var prefix = db_pool_name_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + pool)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// SET_EX_SECRET is used in restoring database.
func set_ex_secret(t *keyval_table, key string, desc *secret_record) bool {
	var prefix = db_secret_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + key)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = db.SetNX(t.ctx, k, v, 0)
	if w.Err() != nil {
		return false
	} else {
		return true
	}
}

func get_secret(t *keyval_table, key string) *secret_record {
	var prefix = db_secret_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + key)
	var w = db.Get(t.ctx, k)
	var desc secret_record
	var ok = load_db_data(w, &desc)
	if ok {
		desc.access_key = key
		return &desc
	} else {
		return nil
	}
}

func delete_secret_unconditionally(t *keyval_table, key string) {
	var prefix = db_secret_prefix
	var db = t.key_prefix_to_db[prefix]
	var k = (prefix + key)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_SECRETS_OF_POOL lists secrets (access-keys) of a pool.  It
// includes a probe-key.  A probe-key is an access-key but has no
// corresponding secret-key.
func list_secrets_of_pool(t *keyval_table, pool string) map[string]*secret_record {
	var prefix = db_secret_prefix
	var keyi = scan_table(t, prefix, "*")
	var descs = map[string]*secret_record{}
	for keyi.Next(t.ctx) {
		var key = keyi.Key()
		var d = get_secret(t, key)
		if d == nil {
			// Race.  It is not an error.
			continue
		}
		//descs = append(descs, d)
		descs[key] = d
	}
	return descs
}

// CLEAR-TABLES.

// CLEAR_ALL clears a keyval-db.  It leaves entries for multiplexer
// entries unless everything.
func clear_all(t *keyval_table, everything bool) {
	for prefix, db := range t.key_prefix_to_db {
		if !everything && prefix == db_mux_ep_prefix {
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
		//panic_non_nil(w.Err())
	}
}

func db_raw_table(t *keyval_table, dbname string) *redis.Client {
	switch dbname {
	case "setting":
		return t.setting
	case "storage":
		return t.storage
	case "process":
		return t.process
	default:
		log.Panic("bad db-name", dbname)
		return nil
	}
}

// SET_DB_RAW sets key-value in a keyval-db intact.
func set_db_raw(t *keyval_table, kv [2]string) {
	if kv[0] == "" || kv[1] == "" {
		panic("keyval empty")
	}
	var prefix = kv[0][:3]
	var db = t.key_prefix_to_db[prefix]
	var w1 = db.Set(t.ctx, kv[0], kv[1], 0)
	panic_non_nil(w1.Err())
}

type db_raw_iterator struct {
	table    *keyval_table
	db       *redis.Client
	iterator *redis.ScanIterator
}

// SCAN_DB_RAW returns an db_raw_iterator.
func scan_db_raw(t *keyval_table, dbname string) *db_raw_iterator {
	var db = db_raw_table(t, dbname)
	return &db_raw_iterator{
		table:    t,
		db:       db,
		iterator: db.Scan(t.ctx, 0, "*", 0).Iterator(),
	}
}

// NEXT_DB_RAW returns a next entry by an iterator.  It return nil at
// end.  It returns a single entry map.  A value is a string of json.
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
				panic(err1)
			}
		}
		return map[string]string{key: string(val)}
	}
	return nil
}

func Table_main() {
	// Check utility functions.

	fmt.Println("Check sorting strings...")
	var x1 = string_sort([]string{"jkl", "ghi", "def", "abc"})
	fmt.Println("sorted strings=", x1)

	fmt.Println("")
	fmt.Println("Check string-set equal...")
	var s1 = []string{
		"uid", "modification_time", "groups", "enabled", "claim",
	}
	var s2 = string_sort([]string{
		"uid", "claim", "groups", "enabled", "modification_time",
	})
	var eq = string_set_equal(s1, s2)
	fmt.Println("equal=", eq)

	// Check JSON Marshal/Unmarshal on integer and strings.

	fmt.Println("")
	fmt.Println("Check marshal/unmarshal string...")
	var b3, err3 = json.Marshal("helo")
	fmt.Println("Marshal(helo)=", string(b3), err3)
	var s4 string
	var err4 = json.Unmarshal(b3, &s4)
	fmt.Println("Unmarshal(helo)=", s4, err4)

	fmt.Println("")
	fmt.Println("Check marshal/unmarshal integer...")
	var b5, err5 = json.Marshal(12345)
	fmt.Println("Marshal(12345)=", string(b5), err5)
	var s6 int
	var err6 = json.Unmarshal(b5, &s6)
	fmt.Println("Unmarshal(12345)=", s6, err6)

	// Check a keyval-db connection.

	fmt.Println("")
	fmt.Println("Check a keyval-db connection...")
	fmt.Println(redis.Version())

	var dbconf = read_db_conf("conf.json")
	var t = make_table(dbconf)

	v1, err1 := t.setting.Get(t.ctx, "uu:m-matsuda").Result()
	if err1 != nil {
		panic(err1)
	}
	fmt.Println("key", v1)
}
