/* Accessors to a Keyval-DB (Valkey/Redis). */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// A table is accessed like a single database, while consists of a set
// of five databases to easy manual inspection in the keyval-DB.
//
// CONSISTENCY OF ENTRIES. uid <-> claim is one-to-one if a user-info
// contains a claim.  Recovery should remove orphaned claims.

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

// DB numbers.
const setting_db = 0
const storage_db = 1
const process_db = 2
const routing_db = 3
const monokey_db = 4

const limit_of_xid_generation_loop = 30

type keyval_table struct {
	ctx     context.Context
	setting *redis.Client
	storage *redis.Client
	process *redis.Client
	routing *redis.Client
	monokey *redis.Client
}

type Fatal struct {
	Err error
}

func (e Fatal) Error() string {
	return fmt.Sprintf("Fatal (%v)", e.Err)
}

func panic_non_nil(w any) {
	if w != nil {
		panic(w)
	}
}

/* SETTING-TABLE */

// Configuration entries "cf:api", "cf:mux", and "cf:mux":mux-name are
// definedin "conf.go".

// "uu":uid entry.
type User_record struct {
	Uid                     string   `json:"uid"`
	Claim                   string   `json:"claim"`
	Groups                  []string `json:"groups"`
	Enabled                 bool     `json:"enabled"`
	Blocked                 bool     `json:"blocked"`
	Ok_terms_and_conditions bool     `json:"ok_terms_and_conditions"`
	Modification_time       int64    `json:"modification_time"`
}

// "um":claim entry is a string.
type user_claim_record string

/* STORAGE-TABLE */

// "po":pool-name entry.
type Pool_record struct {
	Pool              string `json:"pool_name"`
	Owner_uid         string `json:"owner_uid"`
	Owner_gid         string `json:"owner_gid"`
	Buckets_directory string `json:"buckets_directory"`
	Probe_key         string `json:"probe_key"`
	Online_status     bool   `json:"online_status"`
	Expiration_time   int64  `json:"expiration_time"`
	Modification_time int64  `json:"modification_time"`
}

// "ps":pool-name entry.
type Pool_state_record struct {
	State             Pool_state `json:"state"`
	Reason            string     `json:"reason"`
	Modification_time int64      `json:"modification_time"`
}

// "bd":directory entry is a string.
type directory_owner_record string

/* PROCESS-TABLE */

// "ma":pool-name entry.
type Manager_record struct {
	Mux_ep     string `json:"mux_ep"` // mux_host:mux_port
	Start_time int64  `json:"start_time"`
}

// "mn":pool-name entry.  PROCESS_RECORD is about a backend.  A pair
// of root_access and root_secret is a credential for accessing a
// backend.  manager_pid is unused.
type Process_record struct {
	Backend_ep        string `json:"backend_ep"`  // Minio_ep
	Backend_pid       int    `json:"backend_pid"` // Minio_pid
	Root_access       string `json:"root_access"` // Admin
	Root_secret       string `json:"root_secret"` // Password
	Mux_ep            string `json:"mux_ep"`      // Mux_host+Mux_port
	Manager_pid       int    `json:"manager_pid"`
	Modification_time int64  `json:"modification_time"`
}

// "mx":mux-endpoint entry.
type Mux_record struct {
	Mux_ep            string `json:"mux_ep"` // Host+Port
	Start_time        int64  `json:"start_time"`
	Modification_time int64  `json:"modification_time"`
}

/* ROUTING-TABLE */

// "ep":pool-name entry is a string.
type backend_ep_record string

// "bk":bucket-name entry.
type Bucket_record struct {
	Pool              string `json:"pool"`
	Bkt_policy        string `json:"bkt_policy"`
	Modification_time int64  `json:"modification_time"`
}

// "ts":pool-name entry is an int64
type pool_access_timestamp_record int64

// "us":uid entry is an int64
type user_access_timestamp_record int64

/* MONOKEY-TABLE */

// "pi":pool-name entry.
type Pid_record struct {
	Owner_uid         string `json:"owner"`
	Modification_time int64  `json:"modification_time"`
}

// "ky":random entry.
type Key_record struct {
	Owner             string `json:"owner"`
	Secret_key        string `json:"secret_key"`
	Key_policy        string `json:"key_policy"`
	Expiration_time   int64  `json:"expiration_time"`
	Modification_time int64  `json:"modification_time"`
}

// Xid_record is a union of Pid_record|Key_record.
type Xid_record interface{ xid_union() }

func (Pid_record) xid_union() {}
func (Key_record) xid_union() {}

// Enum of states of a pool.
type Pool_state string

const (
	Pool_INITIAL    Pool_state = "initial"
	Pool_READY      Pool_state = "ready"
	Pool_SUSPENDED  Pool_state = "suspended"
	Pool_DISABLED   Pool_state = "disabled"
	Pool_INOPERABLE Pool_state = "inoperable"
)

type name_timestamp_pair struct {
	Name      string
	Timestamp int64
}

type routing_bucket_desc_keys__ struct {
	pool              string
	bkt_policy        string
	modification_time int64
}

// KEY_PAIR is a access-key and a secret-key.
type key_pair struct {
	Access_key string
	Key_record
}

// Enum of random-key usage.
type key_usage string

const (
	Key_POOL key_usage = "pool"
	Key_AKEY key_usage = "akey"
)

func assert_table_prefix_match(t *keyval_table, r *redis.Client, prefix string) {
	var v []string
	switch r {
	case t.setting:
		v = setting_prefixes
	case t.storage:
		v = storage_prefixes
	case t.process:
		v = process_prefixes
	case t.routing:
		v = routing_prefixes
	case t.monokey:
		v = monokey_prefixes
	default:
		panic("intenal: assert_table_prefix_match")
	}
	if !string_search(prefix, v) {
		fmt.Println("setting_prefixes=", setting_prefixes)
		fmt.Println("prefix=", prefix, "v=", v)
		panic("intenal: assert_table_prefix_match")
	}
}

// Makes a key-value DB client.
func make_table(conf Db_conf) *keyval_table {
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
	var routing = redis.NewClient(&redis.Options{
		Addr:     ep,
		Password: pw,
		DB:       routing_db,
	})
	var monokey = redis.NewClient(&redis.Options{
		Addr:     ep,
		Password: pw,
		DB:       monokey_db,
	})
	var t = &keyval_table{
		ctx:     context.Background(),
		setting: setting,
		storage: storage,
		process: process,
		routing: routing,
		monokey: monokey,
	}

	// Wait for a keyval-DB.

	for {
		var s = t.setting.Ping(t.ctx)
		if s.Err() == nil {
			log.Print("Connected to a keyval-DB.")
			return t
		} else {
			log.Print("Connection to a keyval-DB failed (sleeping).")
			time.Sleep(30 * time.Second)
		}
	}
}

// KEY_ITERATOR is a scan result with a key-prefix length.  It removes
// the prefix from a key while iterating.
type key_iterator struct {
	prefix_length int
	i             *redis.ScanIterator
}

func (ki *key_iterator) Err() error {
	return ki.i.Err()
}

func (ki *key_iterator) Next(ctx context.Context) bool {
	return ki.i.Next(ctx)
}

func (ki *key_iterator) Key() string {
	//CHECK-STRING-LENGTH
	var k = ki.i.Val()
	return k[ki.prefix_length:]
}

// SCAN_TABLE returns an iterator of keys for a prefix+target pattern,
// where a target is "*" for a wildcard.  It drops the prefix from the
// returned keys.  Note a null-ness check is always necessary when
// getting a value, because a deletion can intervene scanning keys and
// getting values.
func (t *keyval_table) scan_table(db *redis.Client, prefix string, target string) *key_iterator {
	assert_table_prefix_match(t, db, prefix)
	var pattern = prefix + target
	var prefix_length = len(prefix)
	var ki = key_iterator{
		prefix_length,
		db.Scan(t.ctx, 0, pattern, 0).Iterator()}
	return &ki
}

// LOAD_DATA fills a structure by json data in a keyval-DB.  It
// returns true or false if no entry is found.
func load_data(v *redis.StringCmd, data any) bool {
	var b, err1 = v.Bytes()
	if err1 != nil {
		if err1 == redis.Nil {
			return false
		} else {
			panic(err1)
		}
	}
	var r = bytes.NewReader(b)
	var d = json.NewDecoder(r)
	var err2 = d.Decode(data)
	d.DisallowUnknownFields()
	if err2 != nil {
		log.Panic("Bad json data in a keyval-DB", err2)
	}
	return true
}

func load_data__(v *redis.StringCmd, data any) bool {
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
		panic(fmt.Sprint("Bad json data in a keyval-DB", err1))
	}
	return true
}

/* SETTING-TABLE */

const setting_conf_prefix = "cf:"
const setting_user_info_prefix = "uu:"
const setting_user_claim_prefix = "um:"

var setting_prefixes = string_sort([]string{
	setting_conf_prefix,
	setting_user_info_prefix,
	setting_user_claim_prefix})

// SETTING_CLEAN_CLAIM deletes a claim associated to a uid.  It scans
// all the claims to find an entry associated to a uid.  (This is
// paranoiac because it is called after deleting a claim entry).
func (t *keyval_table) setting_clean_claim(uid string) {
	var db = t.setting
	var keyi = t.scan_table(db, setting_user_claim_prefix, "*")
	for keyi.Next(t.ctx) {
		var k = keyi.Key()
		var xid = t.Setting_get_claim_user(k)
		if *xid == uid {
			var k = (setting_user_claim_prefix + k)
			var w = db.Del(t.ctx, k)
			panic_non_nil(w.Err())
		}
	}
}

func set_conf(t *keyval_table, conf lens3_conf) {
	//var ctx = context.Background()
	var db = t.setting
	switch conf1 := conf.(type) {
	case *Mux_conf:
		var sub = conf1.Subject
		if !(sub == "mux" || (len(sub) >= 5 && sub[:4] == "mux:")) {
			panic("bad conf; subject≠mux")
		}
		var k1 = (setting_conf_prefix + sub)
		var v1, err1 = json.Marshal(conf1)
		if err1 != nil {
			panic(err1)
		}
		// Zero for no expiration.
		var w1 = db.Set(t.ctx, k1, v1, 0)
		panic_non_nil(w1.Err())
	case *Api_conf:
		var sub = conf1.Subject
		if !(sub == "api") {
			panic("bad conf; subject≠api")
		}
		var k2 = (setting_conf_prefix + sub)
		var v2, err1 = json.Marshal(conf1)
		if err1 != nil {
			panic(err1)
		}
		var w2 = db.Set(t.ctx, k2, v2, 0)
		panic_non_nil(w2.Err())
	default:
		log.Panicf("type: (%T) type≠Mux_conf nor type≠Api_conf\n", conf)
	}
}

func (t *keyval_table) Delete_conf(sub string) {
	var db = t.setting
	var k = (setting_conf_prefix + sub)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_CONFS returns a list of confs.  It contains both Mux_conf and
// Api_conf.
func list_confs(t *keyval_table) []lens3_conf {
	var db = t.setting
	var keyi = t.scan_table(db, setting_conf_prefix, "*")
	var confs []lens3_conf
	for keyi.Next(t.ctx) {
		fmt.Println("")
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
			confs = append(confs, v)
		}
	}
	return confs
}

func get_mux_conf(t *keyval_table, sub string) *Mux_conf {
	var db = t.setting
	assert_fatal(sub == "mux" || (len(sub) >= 5 && sub[:4] == "mux:"))
	var k = (setting_conf_prefix + sub)
	var w = db.Get(t.ctx, k)
	var conf Mux_conf
	var ok = load_data(w, &conf)
	if ok {
		//fmt.Println("MUX CONF is", conf)
		check_mux_conf(conf)
		return &conf
	} else {
		return nil
	}
}

func get_api_conf(t *keyval_table, sub string) *Api_conf {
	assert_fatal(sub == "api")
	var db = t.setting
	var k = (setting_conf_prefix + sub)
	var w = db.Get(t.ctx, k)
	var conf Api_conf
	var ok = load_data(w, &conf)
	if ok {
		//fmt.Println("API CONF is", conf)
		check_api_conf(conf)
		return &conf
	} else {
		return nil
	}
}

// ADD_USER adds a user and its claim entry.  A duplicate claim is an
// error.  It deletes an old entry first if exits.
func (t *keyval_table) add_user(ui User_record) {
	var db = t.setting
	var uid = ui.Uid
	var claim = ui.Claim
	assert_fatal(uid != "")
	assert_fatal(len(ui.Groups) > 0)
	if claim != "" {
		var k = (setting_user_claim_prefix + claim)
		var w = db.Get(t.ctx, k)
		var b, err1 = w.Bytes()
		if err1 != nil {
			if err1 == redis.Nil {
			} else {
				panic(err1)
			}
		}
		var xid = string(b)
		if uid != xid {
			var err2 = fmt.Errorf("A claim for {uid} conflicts with {xid}")
			panic(err2)
		}
	}
	t.Delete_user(uid)
	t.set_user_force(ui)
}

// (Use add_user() instead).
func (t *keyval_table) set_user_force(ui User_record) {
	var db = t.setting
	var uid = ui.Uid
	assert_fatal(uid != "")
	var v, err1 = json.Marshal(&ui)
	if err1 != nil {
		panic(err1)
	}
	var k1 = (setting_user_info_prefix + uid)
	var w1 = db.Set(t.ctx, k1, v, 0)
	panic_non_nil(w1.Err())
	var claim = ui.Claim
	if claim != "" {
		var k2 = (setting_user_claim_prefix + claim)
		var w2 = db.Set(t.ctx, k2, v, 0)
		panic_non_nil(w2.Err())
	}
}

// GET_USER gets a user by a uid.  It may return nil.
func (t *keyval_table) Get_user(uid string) *User_record {
	var db = t.setting
	var k = (setting_user_info_prefix + uid)
	var w = db.Get(t.ctx, k)
	var ui User_record
	var ok = load_data(w, &ui)
	if ok {
		return &ui
	} else {
		return nil
	}
}

// SETTING_GET_CLAIM_USER maps a claim to a uid, or returns il.
func (t *keyval_table) Setting_get_claim_user(claim string) *string {
	assert_fatal(claim != "")
	var db = t.setting
	var k = (setting_user_claim_prefix + claim)
	var w = db.Get(t.ctx, k)
	var uid string
	var ok = load_data(w, &uid)
	if ok {
		return &uid
	} else {
		return nil
	}
}

// DELETE_USER deletes a user and its associated claim entry.
func (t *keyval_table) Delete_user(uid string) {
	var ui = t.Get_user(uid)
	if ui == nil {
		return
	}
	var db = t.setting
	var k1 = (setting_user_info_prefix + uid)
	var w1 = db.Del(t.ctx, k1)
	var claim = ui.Claim
	var w2 *redis.IntCmd
	if claim != "" {
		var k2 = (setting_user_claim_prefix + claim)
		w2 = db.Del(t.ctx, k2)
	} else {
		w2 = nil
	}
	t.setting_clean_claim(uid)
	panic_non_nil(w1.Err())
	panic_non_nil(w2.Err())
}

// LIST_USERS lists all uid's.
func (t *keyval_table) List_users() []string {
	var db = t.setting
	var keyi = t.scan_table(db, setting_user_info_prefix, "*")
	var uu []string
	for keyi.Next(t.ctx) {
		uu = append(uu, keyi.Key())
	}
	return uu
}

/* STORAGE-TABLE */

const storage_pool_desc_prefix = "po:"
const storage_pool_state_prefix = "ps:"
const storage_buckets_directory_prefix = "bd:"

var storage_prefixes = string_sort([]string{
	storage_pool_desc_prefix,
	storage_pool_state_prefix,
	storage_buckets_directory_prefix})

func (t *keyval_table) Set_pool(pool string, desc *Pool_record) {
	var db = t.storage
	var k = (storage_pool_desc_prefix + pool)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func (t *keyval_table) Get_pool(pool string) *Pool_record {
	var db = t.storage
	var k = (storage_pool_desc_prefix + pool)
	var w = db.Get(t.ctx, k)
	var desc Pool_record
	var ok = load_data(w, &desc)
	if ok {
		return &desc
	} else {
		return nil
	}
}

func (t *keyval_table) Delete_pool(pool string) {
	var db = t.storage
	var k = (storage_pool_desc_prefix + pool)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_POOLS returns a list of all pool-ID's when the argument is
// "*".  Or, it checks the existence of a pool.
func (t *keyval_table) List_pools(pool string) []string {
	var db = t.storage
	var ki = t.scan_table(db, storage_pool_desc_prefix, pool)
	var pools []string
	for ki.Next(t.ctx) {
		pools = append(pools, ki.Key())
	}
	return pools
}

// SET_EX_BUCKETS_DIRECTORY atomically registers a directory for
// buckets.  At a failure, it returns a current owner, that is,
// (false,owner-uid).  A returned owner could be nil due to a race.
func (t *keyval_table) Set_ex_buckets_directory(path string, pool string) (bool, *string) {
	var k = (storage_buckets_directory_prefix + path)
	var w = t.storage.SetNX(t.ctx, k, pool, 0)
	if w.Err() == nil {
		return true, nil
	}
	var o = t.Get_buckets_directory(path)
	// An ower may be nil by a possible race; it is ignored.
	return false, o
}

func (t *keyval_table) Get_buckets_directory(path string) *string {
	var db = t.storage
	var k = (storage_buckets_directory_prefix + path)
	var w = db.Get(t.ctx, k)
	if w.Err() != nil {
		return nil
	}
	var dir string
	var ok = load_data(w, &dir)
	if ok {
		return &dir
	} else {
		return nil
	}
}

func (t *keyval_table) Get_buckets_directory_of_pool(pool string) *string {
	var db = t.storage
	var ki = t.scan_table(db, storage_buckets_directory_prefix, "*")
	for ki.Next(t.ctx) {
		var path = ki.Key()
		var xid = t.Get_buckets_directory(path)
		if xid != nil && *xid == pool {
			return &path
		}
	}
	return nil
}

func (t *keyval_table) Delete_buckets_directory(path string) {
	var db = t.storage
	var k = (storage_buckets_directory_prefix + path)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

type pool_directory struct {
	directory string
	pool      string
}

// LIST_BUCKETS_DIRECTORIES returns a list of all buckets-directories.
func list_buckets_directories(t *keyval_table) []pool_directory {
	var db = t.storage
	var ki = t.scan_table(db, storage_buckets_directory_prefix, "*")
	var bkts []pool_directory
	for ki.Next(t.ctx) {
		var path = ki.Key()
		var xid = t.Get_buckets_directory(path)
		if xid != nil {
			bkts = append(bkts, pool_directory{
				directory: path,
				pool:      *xid,
			})
		}
	}
	return bkts
}

func (t *keyval_table) Set_pool_state(pool string, state Pool_state, reason string) {
	var db = t.storage
	var now int64 = time.Now().Unix()
	var record = Pool_state_record{
		State:             state,
		Reason:            reason,
		Modification_time: now,
	}
	var k = (storage_pool_state_prefix + pool)
	var v, err = json.Marshal(record)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func (t *keyval_table) Get_pool_state(pool string) *Pool_state_record {
	var db = t.storage
	var k = (storage_pool_state_prefix + pool)
	var w = db.Get(t.ctx, k)
	var state Pool_state_record
	var ok = load_data(w, &state)
	if ok {
		return &state
	} else {
		return nil
	}
}

func (t *keyval_table) Delete_pool_state(pool string) {
	var db = t.storage
	var k = (storage_pool_state_prefix + pool)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

/* PROCESS-TABLE */

const process_minio_manager_prefix = "ma:"
const process_minio_process_prefix = "mn:"
const process_mux_desc_prefix = "mx:"

var process_prefixes = string_sort([]string{
	process_minio_manager_prefix,
	process_minio_process_prefix,
	process_mux_desc_prefix})

// Registers atomically a manager process.  It returns OK/NG, paired
// with a manager that took the role earlier when it fails.  At a
// failure, a returned current owner information can be None due to a
// race (but practically never).
func (t *keyval_table) Set_ex_manager(pool string, desc *Pool_record) (bool, *Manager_record) {
	var db = t.process
	var k = (process_minio_manager_prefix + pool)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = db.SetNX(t.ctx, k, v, 0)
	if w.Err() == nil {
		return true, nil
	} else {
		// Race, returns failure.
		var o = t.Get_manager(pool)
		return false, o
	}
}

func (t *keyval_table) Set_manager_expiry(pool string, timeout int64) {
	var db = t.process
	var k = (process_minio_manager_prefix + pool)
	var w = db.Expire(t.ctx, k, time.Duration(timeout))
	panic_non_nil(w.Err())
}

func (t *keyval_table) Get_manager(pool string) *Manager_record {
	var db = t.process
	var k = (process_minio_manager_prefix + pool)
	var w = db.Get(t.ctx, k)
	var manager Manager_record
	var ok = load_data(w, &manager)
	if ok {
		return &manager
	} else {
		return nil
	}
}

func (t *keyval_table) Delete_manager(pool string) {
	var db = t.process
	var k = (process_minio_manager_prefix + pool)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

func set_backend_proc(t *keyval_table, pool string, desc Process_record) {
	var db = t.process
	var k = (process_minio_process_prefix + pool)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func get_backend_proc(t *keyval_table, pool string) *Process_record {
	var db = t.process
	var k = (process_minio_process_prefix + pool)
	var w = db.Get(t.ctx, k)
	var proc Process_record
	var ok = load_data(w, &proc)
	if ok {
		return &proc
	} else {
		return nil
	}
}

func (t *keyval_table) Delete_minio_proc(pool string) {
	var db = t.process
	var k = (process_minio_process_prefix + pool)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_MINIO_PROCS returns a list of all currently running servers.
func (t *keyval_table) List_minio_procs(pool string) []*Process_record {
	var db = t.process
	var ki = t.scan_table(db, process_minio_process_prefix, pool)
	var procs []*Process_record
	for ki.Next(t.ctx) {
		var id = ki.Key()
		var p = get_backend_proc(t, id)
		if p != nil {
			procs = append(procs, p)
		}
	}
	return procs
}

func (t *keyval_table) Set_mux(mux_ep string, desc *Mux_record) {
	var db = t.process
	var k = (process_mux_desc_prefix + mux_ep)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func (t *keyval_table) Set_mux_expiry(mux_ep string, timeout int64) {
	var db = t.process
	var k = (process_mux_desc_prefix + mux_ep)
	var w = db.Expire(t.ctx, k, time.Duration(timeout))
	panic_non_nil(w.Err())
}

func (t *keyval_table) Get_mux(mux_ep string) *Mux_record {
	var db = t.process
	var k = (process_mux_desc_prefix + mux_ep)
	var w = db.Get(t.ctx, k)
	var desc Mux_record
	var ok = load_data(w, &desc)
	if ok {
		return &desc
	} else {
		return nil
	}
}

func (t *keyval_table) Delete_mux(mux_ep string) {
	var db = t.process
	var k = (process_mux_desc_prefix + mux_ep)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_MUX_EPS returns a list of Mux-record.
func (t *keyval_table) List_muxs() []*Mux_record {
	var db = t.process
	var ki = t.scan_table(db, process_mux_desc_prefix, "*")
	var descs []*Mux_record
	for ki.Next(t.ctx) {
		var ep = ki.Key()
		var d = t.Get_mux(ep)
		if d != nil {
			descs = append(descs, d)
		}
	}
	return descs
}

/* ROUTING-TABLE */

const routing_minio_ep_prefix = "ep:"
const routing_bucket_prefix = "bk:"
const routing_access_timestamp_prefix = "ts:"
const routing_user_timestamp_prefix = "us:"

var routing_prefixes = string_sort([]string{
	routing_minio_ep_prefix,
	routing_bucket_prefix,
	routing_access_timestamp_prefix,
	routing_user_timestamp_prefix,
})

// SET_EX_BUCKET atomically registers a bucket.  It returns OK/NG,
// paired with a pool-id that took the bucket name earlier when it
// fails.  At a failure, a returned current owner information can be
// None due to a race (but practically never).
func (t *keyval_table) Set_ex_bucket(bucket string, desc Bucket_record) (bool, *string) {
	var db = t.routing
	var k = (routing_bucket_prefix + bucket)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = db.SetNX(t.ctx, k, v, 0)
	if w.Err() == nil {
		return true, nil
	} else {
		// Race, returns failure.
		var o = t.Get_bucket(bucket)
		return false, &o.Pool
	}
}

func (t *keyval_table) Get_bucket(bucket string) *Bucket_record {
	var db = t.routing
	var k = (routing_bucket_prefix + bucket)
	var w = db.Get(t.ctx, k)
	var desc Bucket_record
	var ok = load_data(w, &desc)
	if ok {
		return &desc
	} else {
		return nil
	}
}

func (t *keyval_table) Delete_bucket(bucket string) {
	var db = t.routing
	var k = (routing_bucket_prefix + bucket)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

func (t *keyval_table) List_buckets(pool string) []*Bucket_record {
	var db = t.routing
	var ki = t.scan_table(db, routing_bucket_prefix, "*")
	var descs []*Bucket_record
	for ki.Next(t.ctx) {
		var bu = ki.Key()
		var d = t.Get_bucket(bu)
		if d != nil && d.Pool == pool {
			descs = append(descs, d)
		}
	}
	return descs
}

func set_backend_ep(t *keyval_table, pool string, ep string) {
	var db = t.routing
	var k = (routing_minio_ep_prefix + pool)
	//var w = db.Set(t.ctx, k, ep, 0)
	var v, err = json.Marshal(ep)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func get_backend_ep(t *keyval_table, pool string) string {
	var db = t.routing
	var k = (routing_minio_ep_prefix + pool)
	var w = db.Get(t.ctx, k)
	//return w.Value()
	var desc string
	var ok = load_data(w, &desc)
	if ok {
		return desc
	} else {
		return ""
	}
}

func (t *keyval_table) Delete_minio_ep(pool string) {
	var db = t.routing
	var k = (routing_minio_ep_prefix + pool)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

func (t *keyval_table) List_minio_eps() []string {
	var db = t.routing
	var ki = t.scan_table(db, routing_minio_ep_prefix, "*")
	var descs []string
	for ki.Next(t.ctx) {
		var ep = ki.Key()
		var d = get_backend_ep(t, ep)
		if d != "" {
			descs = append(descs, d)
		}
	}
	return descs
}

func (t *keyval_table) Set_access_timestamp(pool string) {
	var db = t.routing
	var k = (routing_access_timestamp_prefix + pool)
	var now int64 = time.Now().Unix()
	var v, err = json.Marshal(now)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func (t *keyval_table) Get_access_timestamp(pool string) int64 {
	var db = t.routing
	var k = (routing_access_timestamp_prefix + pool)
	var w = db.Get(t.ctx, k)
	var desc int64
	var ok = load_data(w, &desc)
	if ok {
		return desc
	} else {
		return 0
	}
}

func (t *keyval_table) Delete_access_timestamp(pool string) {
	var db = t.routing
	var k = (routing_access_timestamp_prefix + pool)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_ACCESS_TIMESTAMPS returns a list of (pool-id, ts) pairs.
func (t *keyval_table) List_access_timestamps() []name_timestamp_pair {
	//return self._routing_table.list_access_timestamps()
	var db = t.routing
	var ki = t.scan_table(db, routing_access_timestamp_prefix, "*")
	var descs []name_timestamp_pair
	for ki.Next(t.ctx) {
		var pool = ki.Key()
		var ts = t.Get_access_timestamp(pool)
		if ts == 0 {
			panic("intenal: List_access_timestamps")
		}
		descs = append(descs, name_timestamp_pair{pool, ts})
	}
	return descs
}

func (t *keyval_table) Set_user_timestamp(uid string) {
	var db = t.routing
	var k = (routing_user_timestamp_prefix + uid)
	var now int64 = time.Now().Unix()
	var v, err = json.Marshal(now)
	panic_non_nil(err)
	var w = db.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

// It returns 0 on an internal db-access error.
func (t *keyval_table) Get_user_timestamp(uid string) int64 {
	var db = t.routing
	var k = (routing_user_timestamp_prefix + uid)
	var w = db.Get(t.ctx, k)
	var desc int64
	var ok = load_data(w, &desc)
	if ok {
		return desc
	} else {
		return 0
	}
}

func (t *keyval_table) Delete_user_timestamp(uid string) {
	var db = t.routing
	var k = (routing_user_timestamp_prefix + uid)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_USER_TIMESTAMPS returns a list of (uid, ts) pairs.
func (t *keyval_table) List_user_timestamps() []name_timestamp_pair {
	var db = t.routing
	var ki = t.scan_table(db, routing_user_timestamp_prefix, "*")
	var descs []name_timestamp_pair
	for ki.Next(t.ctx) {
		var uid = ki.Key()
		var ts = t.Get_user_timestamp(uid)
		if ts == 0 {
			panic("intenal: List_user_timestamps")
		}
		descs = append(descs, name_timestamp_pair{uid, ts})
	}
	return descs
}

/* MONOKEY-TABLE */

const monokey_pid_prefix = "pi:"
const monokey_key_prefix = "ky:"

var monokey_prefixes = string_sort([]string{
	monokey_pid_prefix,
	monokey_key_prefix,
})

func choose_prefix_by_usage(usage key_usage) (string, Xid_record) {
	switch usage {
	case Key_POOL:
		var desc Pid_record
		return monokey_pid_prefix, &desc
	case Key_AKEY:
		var desc Key_record
		return monokey_key_prefix, &desc
	default:
		panic("internal")
	}
}

// MAKE_UNIQUE_XID makes a random unique id for a pool-id (with
// usage="pool") or an access-key (with usage="akey").
func (t *keyval_table) Make_unique_xid(usage key_usage, owner string, info Xid_record) string {
	var db = t.monokey
	var prefix, _ = choose_prefix_by_usage(usage)
	var now int64 = time.Now().Unix()
	var v []byte
	var err error
	switch desc := info.(type) {
	case Pid_record:
		assert_fatal(usage == Key_POOL)
		desc.Owner_uid = owner
		desc.Modification_time = now
		v, err = json.Marshal(desc)
		panic_non_nil(err)
	case Key_record:
		assert_fatal(usage == Key_AKEY)
		desc.Owner = owner
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
		case Pid_record:
			xid = generate_pool_name()
		case Key_record:
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
		if !(xid_generation_loops < limit_of_xid_generation_loop) {
			panic("internal: unique key generation")
		}
	}
}

// SET_EX_XID atomically inserts an id.  It is used at restoring
// database.
func (t *keyval_table) Set_ex_xid(xid string, usage key_usage, desc Xid_record) bool {
	switch desc.(type) {
	case Pid_record:
		assert_fatal(usage == Key_POOL)
	case Key_record:
		assert_fatal(usage == Key_AKEY)
	default:
		panic("internal")
	}
	var db = t.monokey
	var prefix, _ = choose_prefix_by_usage(usage)
	var k = (prefix + xid)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = db.SetNX(t.ctx, k, v, 0)
	if w.Err() != nil {
		return false
	} else {
		return true
	}
}

func (t *keyval_table) Get_xid(usage key_usage, xid string) Xid_record {
	var db = t.monokey
	var prefix, desc = choose_prefix_by_usage(usage)
	var k = (prefix + xid)
	var w = db.Get(t.ctx, k)
	var ok = load_data(w, desc)
	if ok {
		return desc
	} else {
		return nil
	}
}

func (t *keyval_table) Delete_xid_unconditionally(usage key_usage, xid string) {
	var db = t.monokey
	var prefix, _ = choose_prefix_by_usage(usage)
	var k = (prefix + xid)
	var w = db.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_SECRETS_OF_POOL lists secrets (access-keys) of a pool.  It
// includes an probe-key.  A probe-key is an access-key but has no
// corresponding secret-key.
func (t *keyval_table) List_secrets_of_pool(pool string) []key_pair {
	var db = t.monokey
	var ki = t.scan_table(db, monokey_key_prefix, "*")
	var descs []key_pair
	for ki.Next(t.ctx) {
		var key = ki.Key()
		var d = t.Get_xid(Key_AKEY, key)
		if d == nil {
			// Race.
			panic("intenal: List_secrets_of_pool")
		}
		var x = key_pair{Access_key: key, Key_record: d.(Key_record)}
		descs = append(descs, x)
	}
	return descs
}

// CLEAR-TABLES.

// CLEAR_ALL clears a keyva-DB.  It leaves entires for multiplexers unless
// everything.
func (t *keyval_table) Clear_all(everything bool) {
	var db *redis.Client
	db = t.setting
	for _, prefix := range setting_prefixes {
		clear_db(t, db, prefix)
	}
	db = t.storage
	for _, prefix := range storage_prefixes {
		clear_db(t, db, prefix)
	}
	db = t.process
	for _, prefix := range process_prefixes {
		clear_db(t, db, prefix)
	}
	db = t.routing
	for _, prefix := range routing_prefixes {
		clear_db(t, db, prefix)
	}
	db = t.monokey
	for _, prefix := range monokey_prefixes {
		clear_db(t, db, prefix)
	}
}

func clear_db(t *keyval_table, db *redis.Client, prefix string) {
	assert_fatal(len(prefix) == 3)
	var pattern = (prefix + "*")
	var ki = db.Scan(t.ctx, 0, pattern, 0).Iterator()
	for ki.Next(t.ctx) {
		var k = ki.Val()
		var _ = db.Del(t.ctx, k)
		//panic_non_nil(w.Err())
	}
}

func (t *keyval_table) print_all() {
	var db *redis.Client
	db = t.setting
	print_db(t, db, "Setting")
	db = t.storage
	print_db(t, db, "Storage")
	db = t.process
	print_db(t, db, "Process")
	db = t.routing
	print_db(t, db, "Routing")
	db = t.monokey
	print_db(t, db, "Monokey")
}

func print_db(t *keyval_table, db *redis.Client, title string) {
	fmt.Println("---")
	fmt.Println(title)
	var pattern = ("*")
	var ki = db.Scan(t.ctx, 0, pattern, 0).Iterator()
	for ki.Next(t.ctx) {
		var k = ki.Val()
		fmt.Println(k)
	}
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

	// Check a keyval-DB connection.

	fmt.Println("")
	fmt.Println("Check a keyval-DB connection...")
	fmt.Println(redis.Version())

	var dbconf = read_db_conf("conf.json")
	var t = make_table(dbconf)

	v1, err1 := t.setting.Get(t.ctx, "uu:m-matsuda").Result()
	if err1 != nil {
		panic(err1)
	}
	fmt.Println("key", v1)
}
