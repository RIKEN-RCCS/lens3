/* Accessors to Redis DBs. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// A table is accessed like a single database, while it is implemented
// by a couple of databases inside.
//
// CONSISTENCY OF ENTRIES. uid <-> claim is one-to-one if a user-info
// contains a claim.  Recovery removes orphaned claims.

// This is by "go-redis/v8".  Use "go-redis/v8" for Redis-6, or
// "go-redis/v9" for Redis-7.

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/go-redis/redis/v8"
	"log"
	//"sort"
	"time"
	//"slices" >=1.22
	//"reflect"
)

// Redis DB numbers.
const setting_db = 0
const storage_db = 1
const process_db = 2
const routing_db = 3
const monokey_db = 4

const limit_of_xid_generation_loop = 30

type Table struct {
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

type User_info struct {
	User_uid          string
	Claim             string
	Groups            []string
	Enabled           bool
	Modification_time int64
}

type Pool_record struct {
	Pool_name         string
	Owner_uid         string
	Owner_gid         string
	Buckets_directory string
	Probe_key         string
	Online_status     bool
	Expiration_time   int64
	Modification_time int64
}

type Bucket_record struct {
	Directory string
	Pool_name   string
}

// A state of a pool.
type Pool_state string
const (
	INITIAL Pool_state = "initial"
    READY Pool_state = "ready"
    SUSPENDED Pool_state = "suspended"
    DISABLED Pool_state = "disabled"
    INOPERABLE Pool_state = "inoperable"
)

type Pool_state_record struct {
	State Pool_state
	Reason string
	Modification_time int64
}

type Manager_record struct {
	Mux_host string
	Mux_port int64
	Start_time int64
}

type Process_record struct {
	Minio_ep string
	Minio_pid int64
	Admin string
	Password string
	Mux_host string
	Mux_port int64
	Manager_pid int64
	Modification_time int64
}

type Mux_record struct {
	Host string
	Port int64
	Start_time int64
	Modification_time int64
}

func assert_table_prefix_match(t *Table, r *redis.Client, prefix string) {
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
		panic("intenal: assert_table_prefix_match")
	}
}

// Makes Redis clients for a Redis endpoint.
func Get_table() *Table {
	// redis_conf = mux_conf["redis"]
	var addr = "localhost:6378"
	var pw = "fX9LarpFa1P78ukjgaq6PktV2JY94ubFxGq52v5t"
	var setting = redis.NewClient(&redis.Options{
		Addr:     addr,
		Password: pw,
		DB:       setting_db,
	})
	var storage = redis.NewClient(&redis.Options{
		Addr:     addr,
		Password: pw,
		DB:       storage_db,
	})
	var process = redis.NewClient(&redis.Options{
		Addr:     addr,
		Password: pw,
		DB:       process_db,
	})
	var routing = redis.NewClient(&redis.Options{
		Addr:     addr,
		Password: pw,
		DB:       routing_db,
	})
	var monokey = redis.NewClient(&redis.Options{
		Addr:     addr,
		Password: pw,
		DB:       monokey_db,
	})
	var t = new(Table)
	t.ctx = context.Background()
	t.setting = setting
	t.storage = storage
	t.process = process
	t.routing = routing
	t.monokey = monokey

	// Wait for Redis.

	for {
		s := t.setting.Ping(t.ctx)
		if s.Err() == nil {
			log.Print("Connected to Redis.")
			return t
		} else {
			log.Print("Connection to Redis failed (sleeping).")
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
func (t *Table) scan_table(r *redis.Client, prefix string, target string) *key_iterator {
	assert_table_prefix_match(t, r, prefix)
	var pattern = prefix + target
	var prefix_length = len(prefix)
	var ki = key_iterator{
		prefix_length,
		r.Scan(t.ctx, 0, pattern, 0).Iterator()}
	return &ki
}

// LOAD_DATA fills a structure by decoding json data in Redis.  It
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
	var err2 = json.Unmarshal(b, data)
	if err2 != nil {
		panic(fmt.Sprint("Bad json data in Redis", err1))
	}
	return true
}

// SETTING-TABLE.

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
func (t *Table) setting_clean_claim(uid string) {
	var keyi = t.scan_table(t.setting, setting_user_claim_prefix, "*")
	for keyi.Next(t.ctx) {
		var k = keyi.Key()
		var xid = t.Setting_get_claim_user(k)
		if *xid == uid {
			var k = (setting_user_claim_prefix + k)
			var w = t.setting.Del(t.ctx, k)
			panic_non_nil(w.Err())
		}
	}
}

func (t *Table) Set_conf(conf interface{}) {
	//var ctx = context.Background()
	switch conf1 := conf.(type) {
	case Mux_conf:
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
		var w1 = t.setting.Set(t.ctx, k1, v1, 0)
		panic_non_nil(w1.Err())
	case Api_conf:
		var sub = conf1.Subject
		if !(sub == "api") {
			panic("bad conf; subject≠api")
		}
		var k2 = (setting_conf_prefix + sub)
		var v2, err1 = json.Marshal(conf1)
		if err1 != nil {
			panic(err1)
		}
		var w2 = t.setting.Set(t.ctx, k2, v2, 0)
		panic_non_nil(w2.Err())
	default:
		var es = fmt.Sprintf("type %T ≠ Mux_conf nor Api_conf\n", conf)
		panic(es)
	}
}

/*
func (t *Table) delete_conf(sub) {
	return self._setting_table.delete_conf(sub)
}
*/

// LIST_CONFS returns a list of confs.  It contains both Mux_conf and
// Api_conf.
func (t *Table) List_confs() []Lens3_conf {
	var keyi = t.scan_table(t.setting, setting_conf_prefix, "*")
	var confs []Lens3_conf
	for keyi.Next(t.ctx) {
		fmt.Println("")
		var sub = keyi.Key()
		var v Lens3_conf
		switch {
		case sub == "mux" || (len(sub) >= 5 && sub[:4] == "mux:"):
			v = t.get_mux_conf(sub)
		case sub == "api":
			v = t.get_api_conf(sub)
		default:
			panic(fmt.Sprint("Bad subject name"))
		}
		if v != nil {
			confs = append(confs, v)
		}
	}
	return confs
}

func (t *Table) get_mux_conf(sub string) *Mux_conf {
	assert_fatal(sub == "mux" || (len(sub) >= 5 && sub[:4] == "mux:"))
	var k = (setting_conf_prefix + sub)
	var w = t.setting.Get(t.ctx, k)
	var conf Mux_conf
	var ok = load_data(w, &conf)
	if ok {
		fmt.Println("MUX CONF is", conf)
		check_mux_conf(conf)
		return &conf
	} else {
		return nil
	}
}

func (t *Table) get_api_conf(sub string) *Api_conf {
	assert_fatal(sub == "api")
	var k = (setting_conf_prefix + sub)
	var w = t.setting.Get(t.ctx, k)
	var conf Api_conf
	var ok = load_data(w, &conf)
	if ok {
		fmt.Println("API CONF is", conf)
		check_api_conf(conf)
		return &conf
	} else {
		return nil
	}
}

// ADD_USER adds a user and its claim entry.  A duplicate claim is an
// error.  It deletes an old entry first if exits.
func (t *Table) add_user(ui User_info) {
	var uid = ui.User_uid
	var claim = ui.Claim
	assert_fatal(uid != "")
	assert_fatal(len(ui.Groups) > 0)
	if claim != "" {
		var k = (setting_user_claim_prefix + claim)
		var w = t.setting.Get(t.ctx, k)
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
	t.delete_user(uid)
	t.set_user_force(ui)
}

// (Use add_user() instead).
func (t *Table) set_user_force(ui User_info) {
	var uid = ui.User_uid
	assert_fatal(uid != "")
	var v, err1 = json.Marshal(&ui)
	if err1 != nil {
		panic(err1)
	}
	var k1 = (setting_user_info_prefix + uid)
	var w1 = t.setting.Set(t.ctx, k1, v, 0)
	panic_non_nil(w1.Err())
	var claim = ui.Claim
	if claim != "" {
		var k2 = (setting_user_claim_prefix + claim)
		var w2 = t.setting.Set(t.ctx, k2, v, 0)
		panic_non_nil(w2.Err())
	}
}

// GET_USER gets a user by a uid.  It may return nil.
func (t *Table) Get_user(uid string) *User_info {
	var k = (setting_user_info_prefix + uid)
	var w = t.setting.Get(t.ctx, k)
	var ui User_info
	var ok = load_data(w, &ui)
	if ok {
		return &ui
	} else {
		return nil
	}
}

// SETTING_GET_CLAIM_USER maps a claim to a uid, or returns il.
func (t *Table) Setting_get_claim_user(claim string) *string {
	assert_fatal(claim != "")
	var k = (setting_user_claim_prefix + claim)
	var w = t.setting.Get(t.ctx, k)
	var uid string
	var ok = load_data(w, &uid)
	if ok {
		return &uid
	} else {
		return nil
	}
}

// DELETE_USER deletes a user and its associated claim entry.
func (t *Table) delete_user(uid string) {
	var ui = t.Get_user(uid)
	if ui == nil {
		return
	}
	var k1 = (setting_user_info_prefix + uid)
	var w1 = t.setting.Del(t.ctx, k1)
	var claim = ui.Claim
	var w2 *redis.IntCmd
	if claim != "" {
		var k2 = (setting_user_claim_prefix + claim)
		w2 = t.setting.Del(t.ctx, k2)
	} else {
		w2 = nil
	}
	t.setting_clean_claim(uid)
	panic_non_nil(w1.Err())
	panic_non_nil(w2.Err())
}

// LIST_USERS lists uid's.
func (t *Table) List_users() []string {
	var keyi = t.scan_table(t.setting, setting_user_info_prefix, "*")
	var uu []string
	for keyi.Next(t.ctx) {
		uu = append(uu, keyi.Key())
	}
	return uu
}

// STORAGE-TABLE.

const storage_pool_desc_prefix = "po:"
const storage_pool_state_prefix = "ps:"
const storage_buckets_directory_prefix = "bd:"

var storage_prefixes = string_sort([]string{
	storage_pool_desc_prefix,
	storage_pool_state_prefix,
	storage_buckets_directory_prefix})

func (t *Table) Set_pool(pool_id string, desc Pool_record) {
	var k = (storage_pool_desc_prefix + pool_id)
	var v, err1 = json.Marshal(&desc)
	if err1 != nil {
		panic(err1)
	}
	var w2 = t.storage.Set(t.ctx, k, v, 0)
	panic_non_nil(w2.Err())
}

func (t *Table) Get_pool(pool_id string) *Pool_record {
	var k = (storage_pool_desc_prefix + pool_id)
	var w = t.storage.Get(t.ctx, k)
	var desc Pool_record
	var ok = load_data(w, &desc)
	if ok {
		return &desc
	} else {
		return nil
	}
}

func (t *Table) Delete_pool(pool_id string) {
	var k = (storage_pool_desc_prefix + pool_id)
	var w = t.storage.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// LIST_POOLS returns a list of pool-ID's if the argument is "*".  Or,
// it checks the existence of a pool.
func (t *Table) List_pools(pool string) []string {
	var ki = t.scan_table(t.storage, storage_pool_desc_prefix, pool)
	var pools []string
	for ki.Next(t.ctx) {
		pools = append(pools, ki.Key())
	}
	return pools
}

// SET_EX_BUCKETS_DIRECTORY atomically registers a directory for
// buckets.  At a failure, it returns a current owner, that is,
// (false,owner-uid).  A returned owner could be nil due to a race.
func (t *Table) Set_ex_buckets_directory(path string, pool string) (bool, *string) {
	var k = (storage_buckets_directory_prefix + path)
	var w = t.storage.SetNX(t.ctx, k, pool, 0)
	if w.Err() == nil {
		return true, nil
	}
	var o = t.Get_buckets_directory(path)
	// An ower may be nil by a possible race; it is ignored.
	return false, o
}

func (t *Table) Get_buckets_directory(path string) *string {
	var k = (storage_buckets_directory_prefix + path)
	var w = t.storage.Get(t.ctx, k)
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

func (t *Table) Get_buckets_directory_of_pool(pool string) *string {
	var ki = t.scan_table(t.storage, storage_buckets_directory_prefix, "*")
	for ki.Next(t.ctx) {
		var path = ki.Key()
		var xid = t.Get_buckets_directory(path)
		if xid != nil && *xid == pool {
			return &path
		}
	}
	return nil
}

func (t *Table) Delete_buckets_directory(path string) {
	var k = (storage_buckets_directory_prefix + path)
	var w = t.storage.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

func (t *Table) List_buckets_directories() []Bucket_record {
	//return self._storage_table.list_buckets_directories()
	var ki = t.scan_table(t.storage, storage_buckets_directory_prefix, "*")
	var bkts []Bucket_record
	for ki.Next(t.ctx) {
		var path = ki.Key()
		var xid = t.Get_buckets_directory(path)
		if xid != nil {
			bkts = append(bkts, Bucket_record{
				Directory: path,
				Pool_name: *xid,
			})
		}
	}
	return bkts
}

func (t *Table) Set_pool_state(pool string, state Pool_state, reason string) {
	var now int64 = time.Now().Unix()
	var record = Pool_state_record{
		State: state,
		Reason: reason,
		Modification_time: now,
	}
	var k = (storage_pool_state_prefix + pool)
	var v, err = json.Marshal(record)
	panic_non_nil(err)
	var w = t.storage.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func (t *Table) Get_pool_state(pool string) *Pool_state_record {
	var k = (storage_pool_state_prefix + pool)
	var w = t.storage.Get(t.ctx, k)
	var state Pool_state_record
	var ok = load_data(w, &state)
	if ok {
		return &state
	} else {
		return nil
	}
}

func (t *Table) Delete_pool_state(pool string) {
	//self._storage_table.delete_pool_state(pool)
	var k = (storage_pool_state_prefix + pool)
	var w = t.storage.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

// PROCESS-TABLE.

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
func (t *Table) Set_ex_manager(pool string, desc Pool_record) (bool, *Manager_record) {
	var k = (process_minio_manager_prefix + pool)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = t.process.SetNX(t.ctx, k, v, 0)
	if w.Err() == nil {
		return true, nil
	} else {
		// Race, returns failure.
		var o = t.Get_manager(pool)
		return false, o
	}
}

func (t *Table) Set_manager_expiry(pool string, timeout int64) {
	var k = (process_minio_manager_prefix + pool)
	var w = t.process.Expire(t.ctx, k, time.Duration(timeout))
	panic_non_nil(w.Err())
}

func (t *Table) Get_manager(pool string) *Manager_record {
	var k = (process_minio_manager_prefix + pool)
	var w = t.process.Get(t.ctx, k)
	var manager Manager_record
	var ok = load_data(w, &manager)
	if ok {
		return &manager
	} else {
		return nil
	}
}

func (t *Table) Delete_manager(pool string) {
	var k = (process_minio_manager_prefix + pool)
	var w = t.process.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

func (t *Table) Set_minio_proc(pool string, desc Process_record) {
	var k = (process_minio_process_prefix + pool)
	var v, err = json.Marshal(desc)
	panic_non_nil(err)
	var w = t.process.Set(t.ctx, k, v, 0)
	panic_non_nil(w.Err())
}

func (t *Table) Get_minio_proc(pool string) *Process_record {
	var k = (process_minio_process_prefix + pool)
	var w = t.process.Get(t.ctx, k)
	var proc Process_record
	var ok = load_data(w, &proc)
	if ok {
		return &proc
	} else {
		return nil
	}
}

func (t *Table) Delete_minio_proc(pool string) {
	var k = (process_minio_process_prefix + pool)
	var w = t.process.Del(t.ctx, k)
	panic_non_nil(w.Err())
}

func (t *Table) List_minio_procs(pool string) []*Process_record {
	var ki = t.scan_table(t.process, process_minio_process_prefix, pool)
	var procs []*Process_record
	for ki.Next(t.ctx) {
		var id = ki.Key()
		var p = t.Get_minio_proc(id)
		if p != nil {
			procs = append(procs, p)
		}
	}
	return procs
}

/*
func (t *Table) set_mux(self, mux_ep, mux_desc) {
	self._process_table.set_mux(mux_ep, mux_desc)
}

func (t *Table) set_mux_expiry(self, mux_ep, timeout) {
	return self._process_table.set_mux_expiry(mux_ep, timeout)
}

func (t *Table) get_mux(self, mux_ep) {
	return self._process_table.get_mux(mux_ep)
}

func (t *Table) delete_mux(self, mux_ep) {
	self._process_table.delete_mux(mux_ep)
}

func (t *Table) list_muxs(self) {
	return self._process_table.list_muxs()
}

func (t *Table) list_mux_eps(self) {
	return self._process_table.list_mux_eps()
}
*/

// ROUTING-TABLE.

var routing_prefixes = string_sort([]string{})

/*
func (t *Table) set_ex_bucket(self, bucket, desc) {
	return self._routing_table.set_ex_bucket(bucket, desc)
}

func (t *Table) get_bucket(self, bucket) {
	return self._routing_table.get_bucket(bucket)
}

func (t *Table) delete_bucket(self, bucket) {
	self._routing_table.delete_bucket(bucket)
}

func (t *Table) list_buckets(self, pool_id) {
	return self._routing_table.list_buckets(pool_id)
}

func (t *Table) set_minio_ep(self, pool_id, ep) {
	self._routing_table.set_minio_ep(pool_id, ep)
}

func (t *Table) get_minio_ep(self, pool_id) {
	return self._routing_table.get_minio_ep(pool_id)
}

func (t *Table) delete_minio_ep(self, pool_id) {
	self._routing_table.delete_minio_ep(pool_id)
}

func (t *Table) list_minio_ep(self) {
	return self._routing_table.list_minio_ep()
}

func (t *Table) set_access_timestamp(self, pool_id) {
	self._routing_table.set_access_timestamp(pool_id)
}

func (t *Table) get_access_timestamp(self, pool_id) {
	return self._routing_table.get_access_timestamp(pool_id)
}

func (t *Table) delete_access_timestamp(self, pool_id) {
	self._routing_table.delete_access_timestamp(pool_id)
}

func (t *Table) list_access_timestamps(self) {
	return self._routing_table.list_access_timestamps()
}

func (t *Table) set_user_timestamp(self, user_id) {
	return self._routing_table.set_user_timestamp(user_id)
}

func (t *Table) get_user_timestamp(self, pool_id) {
	return self._routing_table.get_user_timestamp(pool_id)
}

func (t *Table) delete_user_timestamp(self, user_id) {
	return self._routing_table.delete_user_timestamp(user_id)
}

func (t *Table) list_user_timestamps(self) {
	return self._routing_table.list_user_timestamps()
}
*/

// MONOKEY-TABLE.

var monokey_prefixes = string_sort([]string{})

/*
func (t *Table) make_unique_xid(self, usage, owner, info) {
	return self._monokey_table.make_unique_xid(usage, owner, info)
}

// Inserts an id, used at database restoring.
func (t *Table) set_ex_xid(self, xid, usage, desc) {
	return self._monokey_table.set_ex_xid(xid, usage, desc)
}

func (t *Table) get_xid(self, usage, xid) {
	return self._monokey_table.get_xid(usage, xid)
}

func (t *Table) delete_xid_unconditionally(self, usage, xid) {
	self._monokey_table.delete_xid_unconditionally(usage, xid)
}

func (t *Table) list_secrets_of_pool(self, pool_id) {
	return self._monokey_table.list_secrets_of_pool(pool_id)
}

// Clear tables.

func (t *Table) clear_all(self, everything) {
	self._setting_table.clear_all(everything)
	self._storage_table.clear_all(everything)
	self._process_table.clear_all(everything)
	self._routing_table.clear_all(everything)
	self._monokey_table.clear_all(everything)
}

func (t *Table) print_all(self) {
	self._setting_table.print_all()
	self._storage_table.print_all()
	self._process_table.print_all()
	self._routing_table.print_all()
	self._monokey_table.print_all()
}
*/

func Table_main() {
	fmt.Println(redis.Version())
	t := Get_table()
	val, err := t.setting.Get(t.ctx, "uu:m-matsuda").Result()
	if err != nil {
		panic(err)
	}
	fmt.Println("key", val)

	var s1 = []string{
		"uid", "modification_time", "groups", "enabled", "claim",
	}
	var s2 = string_sort([]string{
		"uid", "claim", "groups", "enabled", "modification_time",
	})
	var eq = string_set_equal(s1, s2)
	fmt.Println("equal=", eq)
}
