/* A conf-file reader. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Conf-files are read and checked against structures.  It accepts
// extra fields.

import (
	"bytes"
	"encoding/json"
	"fmt"
	//"io"
	"log"
	"os"
	"reflect"
	"slices"
	//"time"
)

// DB_CONF is a pair of an endpoint and password to access a
// keyval-db, and it is usually stored in a file in "etc".
type db_conf struct {
	Ep       string
	Password string
}

// LENS3_CONF is a union of mux_conf|reg_conf.
type lens3_conf interface{ lens3_conf_union() }

func (mux_conf) lens3_conf_union() {}
func (reg_conf) lens3_conf_union() {}

// MUX_CONF is a configuration of Mux.  mux_node_name and log_file are
// optional.
type mux_conf struct {
	Conf_header
	Multiplexer multiplexer_conf `json:"multiplexer"`
	Manager     manager_conf     `json:"manager"`
	Minio       minio_conf       `json:"minio"`
	Rclone      rclone_conf      `json:"rclone"`
	Log_file    string           `json:"log_file"`
	Log_syslog  syslog_conf      `json:"log_syslog"`
}

// REG_CONF is a configuration of Reg.  log_file is optional.
type reg_conf struct {
	Conf_header
	Registrar  registrar_conf `json:"registrar"`
	UI         UI_conf        `json:"ui"`
	Minio      minio_conf     `json:"minio"`
	Log_file   string         `json:"log_file"`
	Log_syslog syslog_conf    `json:"log_syslog"`
}

type Conf_header struct {
	Subject       string `json:"subject"`
	Version       string `json:"version"`
	Aws_signature string `json:"aws_signature"`
}

// NOTE: Trusted_proxy_list should include the fontend proxies and the
// Mux hosts.
type multiplexer_conf struct {
	Port                    int          `json:"port"`
	Front_host              string       `json:"front_host"`
	Trusted_proxy_list      []string     `json:"trusted_proxy_list"`
	Mux_ep_update_interval  time_in_sec  `json:"mux_ep_update_interval"`
	Forwarding_timeout      time_in_sec  `json:"forwarding_timeout"`
	Probe_access_timeout    time_in_sec  `json:"probe_access_timeout"`
	Busy_suspension_time    time_in_sec  `json:"busy_suspension_time"`
	Error_response_delay_ms time_in_sec  `json:"error_response_delay_ms"`
	Mux_node_name           string       `json:"mux_node_name"`
	Backend                 backend_name `json:"backend"`
	Backend_command_timeout time_in_sec  `json:"backend_command_timeout"`
	Mux_access_log_file     string       `json:"mux_access_log_file"`
}

type registrar_conf struct {
	Port                    int           `json:"port"`
	Front_host              string        `json:"front_host"`
	Trusted_proxy_list      []string      `json:"trusted_proxy_list"`
	Base_path               string        `json:"base_path"`
	Claim_uid_map           claim_uid_map `json:"claim_uid_map"`
	User_approval           user_approval `json:"user_approval"`
	Uid_allow_range_list    [][2]int      `json:"uid_allow_range_list"`
	Uid_block_range_list    [][2]int      `json:"uid_block_range_list"`
	Gid_drop_range_list     [][2]int      `json:"gid_drop_range_list"`
	Gid_drop_list           []int         `json:"gid_drop_list"`
	User_expiration_days    int           `json:"user_expiration_days"`
	Pool_expiration_days    int           `json:"pool_expiration_days"`
	Bucket_expiration_days  int           `json:"bucket_expiration_days"`
	Secret_expiration_days  int           `json:"secret_expiration_days"`
	Backend                 backend_name  `json:"backend"`
	Backend_command_timeout time_in_sec   `json:"backend_command_timeout"`
	Probe_access_timeout    time_in_sec   `json:"probe_access_timeout"`
	Postpone_probe_access   bool          `json:"postpone_probe_access"`
	Ui_session_duration     time_in_sec   `json:"ui_session_duration"`
	Reg_access_log_file     string        `json:"reg_access_log_file"`
}

type manager_conf struct {
	Sudo                      string      `json:"sudo"`
	Port_min                  int         `json:"port_min"`
	Port_max                  int         `json:"port_max"`
	Backend_awake_duration    time_in_sec `json:"backend_awake_duration"`
	Backend_start_timeout     time_in_sec `json:"backend_start_timeout"`
	Backend_setup_timeout     time_in_sec `json:"backend_setup_timeout"`
	Backend_command_timeout   time_in_sec `json:"backend_command_timeout"`
	Backend_stop_timeout      time_in_sec `json:"backend_stop_timeout"`
	Backend_no_setup_at_start bool        `json:"backend_no_setup_at_start"`
	Heartbeat_interval        time_in_sec `json:"heartbeat_interval"`
	Heartbeat_timeout         time_in_sec `json:"heartbeat_timeout"`
	Heartbeat_miss_tolerance  int         `json:"heartbeat_miss_tolerance"`
	backend_stabilize_ms      time_in_sec
	backend_linger_ms         time_in_sec

	watch_gap_minimal  time_in_sec
	manager_expiration time_in_sec
}

type minio_conf struct {
	Minio string `json:"minio"`
	Mc    string `json:"mc"`
}

type rclone_conf struct {
	Minio string `json:"minio"`
	Mc    string `json:"mc"`
}

type UI_conf struct {
	S3_url        string `json:"s3_url"`
	Footer_banner string `json:"footer_banner"`
}

type syslog_conf struct {
	Facility string `json:"facility"`
	Priority string `json:"priority"`
}

type time_in_sec int64

type claim_uid_map string

const (
	// claim_uid_map is one of {"id", "email-name", "map"}.
	claim_uid_map_id         claim_uid_map = "id"
	claim_uid_map_email_name claim_uid_map = "email-name"
	claim_uid_map_map        claim_uid_map = "map"
)

var claim_conversions = []claim_uid_map{
	claim_uid_map_id, claim_uid_map_email_name, claim_uid_map_map,
}

type user_approval string

const (
	user_default_allow user_approval = "allow"
	user_default_block user_approval = "block"
)

type backend_name string

const (
	backend_name_minio  backend_name = "minio"
	backend_name_rclone backend_name = "rclone"
)

var backend_list = []backend_name{
	backend_name_minio,
	backend_name_rclone,
}

const bad_message = "Bad json conf-file."

// READ_DB_CONF reads a conf-file for the keyval table.
func read_db_conf(file string) db_conf {
	file = "conf.json"
	var b1, err1 = os.ReadFile(file)
	if err1 != nil {
		log.Panicf("Reading a conf-file failed: file=%s, error=%v", file, err1)
	}
	var b2 = bytes.NewReader(b1)
	var d = json.NewDecoder(b2)
	d.DisallowUnknownFields()
	var conf db_conf
	var err2 = d.Decode(&conf)
	if err2 != nil {
		log.Panic(err2)
	}
	if conf.Ep == "" || conf.Password == "" {
		log.Panic("conf.redis.ep or conf.redis.password missing")
	}
	check_db_entry(conf)
	return conf
}

// Read_conf reads a configuration file and checks a structure is
// properly filled.
func read_conf(filename string) lens3_conf {
	var json1, err1 = os.ReadFile(filename)
	if err1 != nil {
		panic(err1)
	}
	var conf1 = make(map[string]interface{})
	var err2 = json.Unmarshal(json1, &conf1)
	if err2 != nil {
		panic(err2)
	}

	var sub = conf1["subject"].(string)[:3]
	switch sub {
	case "mux":
		var muxconf mux_conf
		var err3 = json.Unmarshal(json1, &muxconf)
		if err3 != nil {
			panic(fmt.Sprint("Bad json conf-file:", err3))
		}
		//fmt.Println("MUX CONF is", muxconf)
		check_mux_conf(&muxconf)
		return &muxconf
	case "reg":
		var regconf reg_conf
		var err4 = json.Unmarshal(json1, &regconf)
		if err4 != nil {
			panic(fmt.Sprint("Bad json conf-file:", err4))
		}
		//fmt.Println("REG CONF is", regconf)
		check_reg_conf(&regconf)
		return &regconf
	default:
		log.Panicf("Bad json conf-file: Bad subject field (%s).", sub)
		return nil
	}
}

func check_mux_conf(conf *mux_conf) {
	check_multiplexer_entry(conf.Multiplexer)
	check_manager_entry(conf.Manager)
	switch conf.Multiplexer.Backend {
	case "minio":
		check_minio_entry(conf.Minio)
	}
	check_syslog_entry(conf.Log_syslog)
}

func check_reg_conf(conf *reg_conf) {
	check_registrar_entry(conf.Registrar)
	switch conf.Registrar.Backend {
	case "minio":
		check_minio_entry(conf.Minio)
	}
	check_ui_entry(conf.UI)
	check_syslog_entry(conf.Log_syslog)
}

func assert_slot(c bool) {
	if !c {
		panic(fmt.Errorf("Bad conf-file."))
	}
}

func check_db_entry(e db_conf) {
	if len(e.Ep) > 0 && len(e.Password) > 0 {
	} else {
		log.Panic(fmt.Errorf(bad_message))
	}
}

func check_field_required_and_positive(t any, slot string) {
	var t1 = reflect.ValueOf(t)
	var s = t1.FieldByName(slot)
	//fmt.Printf("s=%T %v\n", s, s)
	assert_fatal(s.IsValid())
	switch s.Kind() {
	case reflect.Int:
		fallthrough
	case reflect.Int8:
		fallthrough
	case reflect.Int16:
		fallthrough
	case reflect.Int32:
		fallthrough
	case reflect.Int64:
		var x1 = s.Int()
		if !(!s.IsZero() && x1 > 0) {
			log.Panicf("field (%s) is required in %T.", slot, t)
		}
	case reflect.String:
		if s.IsZero() {
			log.Panicf("field (%s) is required in %T.", slot, t)
		}
	}
}

func check_multiplexer_entry(e multiplexer_conf) {
	for _, slot := range []string{
		"Port",
		"Front_host",
		//"Trusted_proxy_list",
		"Mux_ep_update_interval",
		"Forwarding_timeout",
		"Probe_access_timeout",
		"Error_response_delay_ms",
		"Busy_suspension_time",
		//"Mux_node_name",
		"Backend",
		"Backend_command_timeout",
		"Mux_access_log_file",
	} {
		check_field_required_and_positive(e, slot)
	}
	if !slices.Contains(backend_list, e.Backend) {
		panic(fmt.Errorf(bad_message))
	}
}

func check_registrar_entry(e registrar_conf) {
	for _, slot := range []string{
		"Port",
		"Front_host",
		// "Trusted_proxy_list",
		// "Base_path",
		"Claim_uid_map",
		"User_approval",
		// "Uid_allow_range_list",
		// "Uid_block_range_list",
		// "Gid_drop_range_list",
		// "Gid_drop_list",
		"User_expiration_days",
		"Pool_expiration_days",
		"Bucket_expiration_days",
		"Secret_expiration_days",
		"Backend",
		"Backend_command_timeout",
		"Probe_access_timeout",
		"Postpone_probe_access",
		"Ui_session_duration",
		"Reg_access_log_file",
	} {
		check_field_required_and_positive(e, slot)
	}
	if !slices.Contains(claim_conversions, e.Claim_uid_map) {
		panic(fmt.Errorf(bad_message))
	}
	if !slices.Contains(backend_list, e.Backend) {
		panic(fmt.Errorf(bad_message))
	}
}

func check_manager_entry(e manager_conf) {
	for _, slot := range []string{
		"Sudo",
		"Port_min",
		"Port_max",
		"Backend_awake_duration",
		"Backend_start_timeout",
		"Backend_setup_timeout",
		"Backend_stop_timeout",
		"Backend_command_timeout",
		"Backend_no_setup_at_start",
		"Heartbeat_interval",
		"Heartbeat_miss_tolerance",
		"Heartbeat_timeout",
	} {
		check_field_required_and_positive(e, slot)
	}
}

func check_minio_entry(e minio_conf) {
	if len(e.Minio) > 0 &&
		len(e.Mc) > 0 {
	} else {
		panic(fmt.Errorf(bad_message))
	}
}

func check_ui_entry(e UI_conf) {
	if len(e.S3_url) > 0 &&
		len(e.Footer_banner) > 0 {
	} else {
		panic(fmt.Errorf(bad_message))
	}
}

func check_syslog_entry(e syslog_conf) {
	if len(e.Facility) > 0 &&
		len(e.Priority) > 0 {
	} else {
		panic(fmt.Errorf(bad_message))
	}
}

// func check_registrar_entry_2(e registrar_conf) {
// 	if e.Port > 0 &&
// 		e.Front_host != "" &&
// 		// e.Trusted_proxies
// 		// e.Base_path != "" &&
// 		slices.Contains(claim_conversions, e.Claim_uid_map) &&
// 		e.Probe_access_timeout > 0 &&
// 		e.Backend_command_timeout > 0 &&
// 		e.Max_pool_expiry > 0 &&
// 		e.Csrf_secret_seed != "" &&
// 		e.Backend != "" &&
// 		e.Backend_command_timeout > 0 &&
// 		e.Reg_access_log_file != "" {
// 	} else {
// 		panic(fmt.Errorf(bad_message))
// 	}
// }

// func check_multiplexer_entry_2(e multiplexer_conf) {
// 	if e.Port > 0 &&
// 		e.Front_host != "" &&
// 		// e.Trusted_proxies
// 		e.Mux_ep_update_interval > 0 &&
// 		e.Forwarding_timeout > 0 &&
// 		e.Probe_access_timeout > 0 &&
// 		e.Error_response_delay_ms > 0 &&
// 		e.Busy_suspension_time > 0 &&
// 		//e.Mux_node_name
// 		e.Backend != "" &&
// 		e.Backend_command_timeout > 0 &&
// 		e.Mux_access_log_file != "" {
// 	} else {
// 		panic(fmt.Errorf(bad_message))
// 	}
// }

// func check_manager_entry_2(e manager_conf) {
// 	assert_slot(len(e.Sudo) > 0)
// 	assert_slot(e.Port_min > 0)
// 	assert_slot(e.Port_max > 0)
// 	assert_slot(e.Backend_awake_duration > 0)
// 	//assert_slot(Backend_setup_at_start : bool
// 	assert_slot(e.Backend_start_timeout > 0)
// 	assert_slot(e.Backend_setup_timeout > 0)
// 	assert_slot(e.Backend_stop_timeout > 0)
// 	assert_slot(e.Backend_command_timeout > 0)
// 	assert_slot(e.Heartbeat_interval > 0)
// 	assert_slot(e.Heartbeat_miss_tolerance > 0)
// 	assert_slot(e.Heartbeat_timeout > 0)
// }
