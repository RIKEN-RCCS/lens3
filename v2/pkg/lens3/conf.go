/* A conf file reader. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Configuration Files.  The configurations are stored in the
// keyval-db.  Configuration files are read and checked against the
// structures.  It accepts extra fields.  Reading configuration files
// are by the admin tool, and the errors are fatal.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"reflect"
	"slices"
)

// DB_CONF is a pair of an endpoint and a password to access the
// keyval-db.
type db_conf struct {
	Ep       string
	Password string
}

// LENS3_CONF is a union of mux_conf|reg_conf.
type lens3_conf interface{ lens3_conf_union() }

func (mux_conf) lens3_conf_union() {}
func (reg_conf) lens3_conf_union() {}

// MUX_CONF is a configuration of Multiplexer.
type mux_conf struct {
	Conf_header
	Multiplexer multiplexer_conf `json:"multiplexer"`
	Manager     manager_conf     `json:"manager"`
	Minio       minio_conf       `json:"minio"`
	Rclone      rclone_conf      `json:"rclone"`
	Log         access_log_conf  `json:"log"`
	Logging     *logging_conf    `json:"logging"`
}

// REG_CONF is a configuration of Registrar.
type reg_conf struct {
	Conf_header
	Registrar registrar_conf  `json:"registrar"`
	UI        UI_conf         `json:"ui"`
	Log       access_log_conf `json:"log"`
	Logging   *logging_conf   `json:"logging"`
}

type Conf_header struct {
	Subject       string `json:"subject"`
	Version       string `json:"version"`
	Aws_signature string `json:"aws_signature"`
}

// MULTIPLEXER_CONF is the Mux part of a configuration.  mux_node_name
// is optional.  NOTE: Trusted_proxy_list should include the frontend
// proxies and the Mux hosts.
type multiplexer_conf struct {
	Port                    int          `json:"port"`
	Trusted_proxy_list      []string     `json:"trusted_proxy_list"`
	Mux_node_name           string       `json:"mux_node_name"`
	Backend                 backend_name `json:"backend"`
	Mux_ep_update_interval  time_in_sec  `json:"mux_ep_update_interval"`
	Forwarding_timeout      time_in_sec  `json:"forwarding_timeout"`
	Probe_access_timeout    time_in_sec  `json:"probe_access_timeout"`
	Busy_suspension_time    time_in_sec  `json:"busy_suspension_time"`
	Error_response_delay_ms time_in_sec  `json:"error_response_delay_ms"`
	Backend_timeout_ms      time_in_sec  `json:"backend_timeout_ms"`
}

// REGISTRAR_CONF is a Registrar configuration.  SERVER_EP is a
// host:port that is used by the frontend proxy to refer to Registrar.
type registrar_conf struct {
	Port                    int           `json:"port"`
	Server_ep               string        `json:"server_ep"`
	Trusted_proxy_list      []string      `json:"trusted_proxy_list"`
	Base_path               string        `json:"base_path"`
	Claim_uid_map           claim_uid_map `json:"claim_uid_map"`
	User_approval           user_approval `json:"user_approval"`
	Postpone_probe_access   bool          `json:"postpone_probe_access"`
	Uid_allow_range_list    [][2]int      `json:"uid_allow_range_list"`
	Uid_block_range_list    [][2]int      `json:"uid_block_range_list"`
	Gid_drop_range_list     [][2]int      `json:"gid_drop_range_list"`
	Gid_drop_list           []int         `json:"gid_drop_list"`
	User_expiration_days    int           `json:"user_expiration_days"`
	Pool_expiration_days    int           `json:"pool_expiration_days"`
	Bucket_expiration_days  int           `json:"bucket_expiration_days"`
	Secret_expiration_days  int           `json:"secret_expiration_days"`
	Error_response_delay_ms time_in_sec   `json:"error_response_delay_ms"`
	Backend_timeout_ms      time_in_sec   `json:"backend_timeout_ms"`
	Probe_access_timeout    time_in_sec   `json:"probe_access_timeout"`
	Ui_session_duration     time_in_sec   `json:"ui_session_duration"`
}

type manager_conf struct {
	Sudo                      string      `json:"sudo"`
	Port_min                  int         `json:"port_min"`
	Port_max                  int         `json:"port_max"`
	Backend_awake_duration    time_in_sec `json:"backend_awake_duration"`
	Backend_start_timeout     time_in_sec `json:"backend_start_timeout"`
	Backend_setup_timeout     time_in_sec `json:"backend_setup_timeout"`
	Backend_stop_timeout      time_in_sec `json:"backend_stop_timeout"`
	Backend_timeout_ms        time_in_sec `json:"backend_timeout_ms"`
	Backend_region            string      `json:"backend_region"`
	Backend_no_setup_at_start bool        `json:"backend_no_setup_at_start"`
	Heartbeat_interval        time_in_sec `json:"heartbeat_interval"`
	Heartbeat_timeout         time_in_sec `json:"heartbeat_timeout"`
	Heartbeat_miss_tolerance  int         `json:"heartbeat_miss_tolerance"`
	backend_stabilize_ms      time_in_sec
	backend_linger_ms         time_in_sec
	watch_gap_minimal         time_in_sec
	manager_expiration        time_in_sec
	busy_suspension_duration  time_in_sec
}

type minio_conf struct {
	Minio string `json:"minio"`
	Mc    string `json:"mc"`
}

type rclone_conf struct {
	Rclone          string   `json:"rclone"`
	Command_options []string `json:"command_options"`
}

type UI_conf struct {
	S3_url        string `json:"s3_url"`
	Footer_banner string `json:"footer_banner"`
}

type access_log_conf struct {
	Access_log_file string `json:"access_log_file"`
}

// LOGGING_CONF is optional.  It can be a member of both Multiplexer and
// Registrar, and prefers one in Multiplexer.
type logging_conf struct {
	Logger logger_conf `json:"logger"`
	Stats  stats_conf  `json:"stats"`
	Alert  alert_conf  `json:"alert"`
	Mqtt   mqtt_conf   `json:"mqtt"`
}

type logger_conf struct {
	Log_file    string `json:"log_file"`
	Facility    string `json:"facility"`
	Level       string `json:"level"`
	Verbosity   int    `json:"verbosity"`
	Source_line bool   `json:"source_line"`
}

type stats_conf struct {
	Period time_in_sec `json:"period"`
}

type alert_conf struct {
	Queue string `json:"queue"`
	Level string `json:"level"`
}

type mqtt_conf struct {
	Ep       string `json:"ep"`
	Client   string `json:"client"`
	Topic    string `json:"topic"`
	Username string `json:"username"`
	Password string `json:"password"`
}

type time_in_sec int64

// CLAIM_UID_MAP is one of {"id", "email-name", "map"}.
type claim_uid_map string

const (
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

const bad_message = "Bad json conf file."

// READ_DB_CONF reads a conf file for the keyval-db.
func read_db_conf(filepath string) *db_conf {
	var b1, err1 = os.ReadFile(filepath)
	if err1 != nil {
		slogger.Error("Reading a db conf file failed",
			"file", filepath, "err", err1)
		return nil
	}
	var b2 = bytes.NewReader(b1)
	var d = json.NewDecoder(b2)
	d.DisallowUnknownFields()
	var conf db_conf
	var err2 = d.Decode(&conf)
	if err2 != nil {
		slogger.Error("Reading a db conf file failed",
			"file", filepath, "err", err2)
		return nil
	}
	if conf.Ep == "" || conf.Password == "" {
		slogger.Error("Reading a db conf file failed",
			"file", filepath, "err", fmt.Errorf("empty entries"))
		return nil
	}
	return &conf
}

// READ_CONF reads a configuration file and checks a structure is
// properly filled.
func read_conf(filename string) lens3_conf {
	var json1, err1 = os.ReadFile(filename)
	if err1 != nil {
		slogger.Error("os.ReadFile() failed", "file", filename)
		return nil
	}
	var conf1 = make(map[string]any)
	var err2 = json.Unmarshal(json1, &conf1)
	if err2 != nil {
		slogger.Error("Bad json format", "file", filename, "err", err2)
		return nil
	}

	var sub = conf1["subject"].(string)[:3]
	switch sub {
	case "mux":
		var muxconf mux_conf
		var err3 = json.Unmarshal(json1, &muxconf)
		if err3 != nil {
			slogger.Error("Bad json format", "file", filename, "err", err3)
			return nil
		}
		//fmt.Println("MUX CONF is", muxconf)
		check_mux_conf(&muxconf)
		return &muxconf
	case "reg":
		var regconf reg_conf
		var err4 = json.Unmarshal(json1, &regconf)
		if err4 != nil {
			slogger.Error("Bad json format", "file", filename, "err", err4)
			return nil
		}
		//fmt.Println("REG CONF is", regconf)
		check_reg_conf(&regconf)
		return &regconf
	default:
		slogger.Error("Bad conf file, bad subject",
			"file", filename, "subject", sub)
		return nil
	}
}

func check_mux_conf(conf *mux_conf) {
	check_multiplexer_entry(&conf.Multiplexer)
	check_manager_entry(&conf.Manager)
	switch conf.Multiplexer.Backend {
	case "minio":
		check_minio_entry(&conf.Minio)
	case "rclone":
		check_rclone_entry(&conf.Rclone)
	}
	check_access_log_entry(&conf.Log)
}

func check_reg_conf(conf *reg_conf) {
	check_registrar_entry(&conf.Registrar)
	check_ui_entry(&conf.UI)
	check_access_log_entry(&conf.Log)
	if conf.Logging != nil {
		check_logging_entry(conf.Logging)
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
			slogger.Error(fmt.Sprintf("field %s is required in %T", slot, t))
			panic(nil)
		}
	case reflect.String:
		if s.IsZero() {
			slogger.Error(fmt.Sprintf("field %s is required in %T", slot, t))
			panic(nil)
		}
	}
}

func check_multiplexer_entry(e *multiplexer_conf) {
	for _, slot := range []string{
		"Port",
		//"Front_host",
		//"Trusted_proxy_list",
		//"Mux_node_name",
		"Backend",
		"Mux_ep_update_interval",
		"Forwarding_timeout",
		"Probe_access_timeout",
		"Busy_suspension_time",
		"Error_response_delay_ms",
		"Backend_timeout_ms",
	} {
		check_field_required_and_positive(*e, slot)
	}
	if !slices.Contains(backend_list, e.Backend) {
		slogger.Error("Bad backend name", "name", e.Backend)
		panic(nil)
	}
}

func check_registrar_entry(e *registrar_conf) {
	for _, slot := range []string{
		//"Backend",
		"Port",
		"Server_ep",
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
		"Error_response_delay_ms",
		"Backend_timeout_ms",
		"Probe_access_timeout",
		"Postpone_probe_access",
		"Ui_session_duration",
	} {
		check_field_required_and_positive(*e, slot)
	}
	if !slices.Contains(claim_conversions, e.Claim_uid_map) {
		slogger.Error("Bad claim mapping", "name", e.Claim_uid_map)
		panic(nil)
	}
}

func check_manager_entry(e *manager_conf) {
	for _, slot := range []string{
		"Sudo",
		"Port_min",
		"Port_max",
		"Backend_awake_duration",
		"Backend_start_timeout",
		"Backend_setup_timeout",
		"Backend_stop_timeout",
		"Backend_timeout_ms",
		"Backend_region",
		"Backend_no_setup_at_start",
		"Heartbeat_interval",
		"Heartbeat_miss_tolerance",
		"Heartbeat_timeout",
	} {
		check_field_required_and_positive(*e, slot)
	}
}

func check_minio_entry(e *minio_conf) {
	if len(e.Minio) > 0 && len(e.Mc) > 0 {
		// OK.
	} else {
		slogger.Error("Bad backend entry (minio)", "entry", e)
		panic(nil)
	}
}

func check_rclone_entry(e *rclone_conf) {
	if len(e.Rclone) > 0 {
		// OK.
	} else {
		slogger.Error("Bad backend entry (rclone)", "entry", e)
		panic(nil)
	}
}

func check_ui_entry(e *UI_conf) {
	if len(e.S3_url) > 0 &&
		len(e.Footer_banner) > 0 {
		// OK.
	} else {
		slogger.Error("Bad S3 endpoint", "entry", e)
		panic(nil)
	}
}

func check_access_log_entry(e *access_log_conf) {
	for _, slot := range []string{
		"Access_log_file",
	} {
		check_field_required_and_positive(*e, slot)
	}
}

func check_logging_entry(e *logging_conf) {
	check_logger_entry(&e.Logger)
	check_alert_entry(&e.Alert)
	if e.Alert.Queue == "mqtt" {
		check_mqtt_entry(&e.Mqtt)
	}
}

func check_logger_entry(e *logger_conf) {
	if len(e.Facility) > 0 && len(e.Level) > 0 {
		// OK.
	} else {
		slogger.Error("Bad logger entry", "entry", e)
		panic(nil)
	}
}

func check_alert_entry(e *alert_conf) {
	if len(e.Level) > 0 {
		// OK.
	} else {
		slogger.Error("Bad alert entry", "entry", e)
		panic(nil)
	}
}

func check_mqtt_entry(e *mqtt_conf) {
	if len(e.Ep) > 0 {
		// OK.
	} else {
		slogger.Error("Bad MQTT entry", "entry", e)
		panic(nil)
	}
}

// func check_registrar_entry_2(e registrar_conf) {
// 	if e.Port > 0 &&
// 		e.Front_host != "" &&
// 		// e.Trusted_proxies
// 		// e.Base_path != "" &&
// 		slices.Contains(claim_conversions, e.Claim_uid_map) &&
// 		e.Probe_access_timeout > 0 &&
// 		e.Backend_timeout_ms > 0 &&
// 		e.Max_pool_expiry > 0 &&
// 		e.Csrf_secret_seed != "" &&
// 		e.Backend != "" &&
// 		e.Backend_timeout_ms > 0 &&
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
// 		e.Backend_timeout_ms > 0 &&
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
// 	assert_slot(e.Backend_timeout_ms > 0)
// 	assert_slot(e.Heartbeat_interval > 0)
// 	assert_slot(e.Heartbeat_miss_tolerance > 0)
// 	assert_slot(e.Heartbeat_timeout > 0)
// }
