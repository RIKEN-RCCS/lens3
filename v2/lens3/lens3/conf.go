/* A conf file reader. */

// Copyright 2022-2024 RIKEN R-CCS
// SPDX-License-Identifier: BSD-2-Clause

package lens3

// Configuration Files.  The configurations are stored in the
// keyval-db.  Configuration files are read and checked against
// definitions.  It accepts extra fields.  Reading configuration files
// are by the admin tool, and the errors are fatal.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"reflect"
	"slices"
	"strings"
	"time"
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
	Error_response_delay_ms time_in_ms   `json:"error_response_delay_ms"`
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
	Uid_allow_range_list    [][2]int      `json:"uid_allow_range_list"`
	Uid_block_range_list    [][2]int      `json:"uid_block_range_list"`
	Gid_drop_range_list     [][2]int      `json:"gid_drop_range_list"`
	Gid_drop_list           []int         `json:"gid_drop_list"`
	User_expiration_days    time_in_day   `json:"user_expiration_days"`
	Pool_expiration_days    time_in_day   `json:"pool_expiration_days"`
	Bucket_expiration_days  time_in_day   `json:"bucket_expiration_days"`
	Secret_expiration_days  time_in_day   `json:"secret_expiration_days"`
	Error_response_delay_ms time_in_ms    `json:"error_response_delay_ms"`
	Ui_session_duration     time_in_sec   `json:"ui_session_duration"`
	//Postpone_probe_access   bool          `json:"postpone_probe_access"`
}

type manager_conf struct {
	Sudo                      string      `json:"sudo"`
	Port_min                  int         `json:"port_min"`
	Port_max                  int         `json:"port_max"`
	Backend_awake_duration    time_in_sec `json:"backend_awake_duration"`
	Backend_start_timeout_ms  time_in_ms  `json:"backend_start_timeout_ms"`
	Backend_timeout_ms        time_in_ms  `json:"backend_timeout_ms"`
	Backend_region            string      `json:"backend_region"`
	Backend_no_setup_at_start bool        `json:"backend_no_setup_at_start"`
	Heartbeat_interval        time_in_sec `json:"heartbeat_interval"`
	Heartbeat_miss_tolerance  int         `json:"heartbeat_miss_tolerance"`
	backend_suspension_time   time.Duration
	backend_stabilize_time    time.Duration
	backend_linger_time       time.Duration
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
	Logger logger_conf  `json:"logger"`
	Stats  stats_conf   `json:"stats"`
	Alert  *alert_conf  `json:"alert"`
	Syslog *syslog_conf `json:"syslog"`
	Mqtt   *mqtt_conf   `json:"mqtt"`
}

type logger_conf struct {
	Log_file    string     `json:"log_file"`
	Level       string     `json:"level"`
	Tracing     trace_flag `json:"tracing"`
	Source_line bool       `json:"source_line"`
}

type stats_conf struct {
	Sample_period time_in_sec `json:"sample_period"`
}

type alert_conf struct {
	Queue string `json:"queue"`
	Level string `json:"level"`
}

type syslog_conf struct {
	Facility string `json:"facility"`
}

type mqtt_conf struct {
	Ep       string `json:"ep"`
	Client   string `json:"client"`
	Topic    string `json:"topic"`
	Username string `json:"username"`
	Password string `json:"password"`
}

type time_in_sec int64
type time_in_ms int64
type time_in_day int

func (t time_in_sec) time_duration() time.Duration {
	var d = (time.Duration(t) * time.Second)
	return d
}

func (t time_in_ms) time_duration() time.Duration {
	var d = (time.Duration(t) * time.Millisecond)
	return d
}

func (t time_in_day) time_duration() time.Duration {
	var zero time.Time
	var d = zero.AddDate(0, 0, int(t)).Sub(zero)
	return d
}

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

func check_field_required_and_positive(t any, slot string, conf_name string) {
	var t1 = reflect.ValueOf(t)
	var s = t1.FieldByName(slot)
	//fmt.Printf("s=%T %v\n", s, s)
	if !s.IsValid() {
		var slot1 = strings.ToLower(slot)
		fmt.Printf("Required %q not in %q configuration.\n", slot1, conf_name)
		panic(nil)
	}
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
		"Error_response_delay_ms",
	} {
		check_field_required_and_positive(*e, slot, "multiplexer")
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
		"Ui_session_duration",
		//"Postpone_probe_access",
	} {
		check_field_required_and_positive(*e, slot, "registrar")
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
		"Backend_start_timeout_ms",
		"Backend_timeout_ms",
		"Backend_region",
		"Backend_no_setup_at_start",
		"Heartbeat_interval",
		"Heartbeat_miss_tolerance",
	} {
		check_field_required_and_positive(*e, slot, "manager")
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
		check_field_required_and_positive(*e, slot, "log")
	}
}

func check_logging_entry(e *logging_conf) {
	check_logger_entry(&e.Logger)
	if e.Alert != nil {
		check_alert_entry(e.Alert)
	}
	if e.Syslog != nil {
		check_syslog_entry(e.Syslog)
	}
	if e.Mqtt != nil {
		check_mqtt_entry(e.Mqtt)
	}
}

func check_logger_entry(e *logger_conf) {
	if len(e.Log_file) > 0 && len(e.Level) > 0 {
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

func check_syslog_entry(e *syslog_conf) {
	if len(e.Facility) > 0 {
		// OK.
	} else {
		slogger.Error("Bad Syslog entry", "entry", e)
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
