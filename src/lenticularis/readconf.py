"""A config file reader."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import jsonschema
import os
import yaml

##default_mux_conf = "/etc/lenticularis/mux-config.yaml"
mux_conf_envname = "LENTICULARIS_MUX_CONFIG"

##default_adm_conf = "/etc/lenticularis/adm-config.yaml"
adm_conf_envname = "LENTICULARIS_ADM_CONFIG"

node_envname = "LENTICULARIS_MUX_NODE"


def read_mux_conf(configfile=None):
    return readconf(configfile, fix_mux_conf, validate_mux_conf,
                    mux_conf_envname)


def read_adm_conf(configfile=None):
    return readconf(configfile, fix_adm_conf, validate_adm_conf,
                    adm_conf_envname)


def readconf(configfile, fixfn, valfn, envname):
    if configfile is None:
        configfile = os.environ.get(envname)
        pass
    assert configfile is not None
    try:
        with open(configfile, "r") as f:
            yamlconf = yaml.load(f, Loader=yaml.BaseLoader)
    except yaml.YAMLError as e:
        raise Exception(f"Read config file failed: {configfile}; exception={e}")
    except Exception as e:
        raise Exception(f"Read config file failed: {configfile} exception={e}")
    conf = fixfn(yamlconf)
    valfn(conf)
    return (conf, configfile)


def gunicorn_schema(number_type):
    sc = {
        "type": "object",
        "properties": {
            "port": {"type": "string"},
            "workers": number_type,
            "threads": number_type,
            "timeout": number_type,
            "access_logfile": {"type": "string"},
            "log_file": {"type": "string"},
            "log_level": {"type": "string"},
            "log_syslog_facility": {"type": "string"},
            "reload": {"type": "string"},
        },
        "required": [
            "port",
        ],
        "additionalProperties": False,
    }
    return sc


def redis_schema(number_type):
    sc = {
        "type": "object",
        "properties": {
            "host": {"type": "string"},
            "port": number_type,
            "password": {"type": "string"},
        },
        "required": [
            "host",
            "port",
            "password",
        ],
        "additionalProperties": False,
    }
    return sc


def syslog_schema():
    sc = {
        "type": "object",
        "properties": {
            "facility": {"type": "string"},
            "priority": {"type": "string"},
        },
        "required": [
            "facility",
            "priority",
        ],
        "additionalProperties": False,
    }
    return sc


def mux_schema(number_type):
    multiplexer = {
        "type": "object",
        "properties": {
            "facade_hostname": {"type": "string"},
            "trusted_proxies": {"type": "array", "items": {"type": "string"}},
            "mux_ep_update_interval": number_type,
            "forwarding_timeout": number_type,
            "probe_access_timeout": number_type,
        },
        "required": [
            "facade_hostname",
            "trusted_proxies",
            "mux_ep_update_interval",
            "forwarding_timeout",
            "probe_access_timeout",
        ],
        "additionalProperties": False,
    }
    minio_manager = {
        "type": "object",
        "properties": {
            "port_min": number_type,
            "port_max": number_type,
            "sudo": {"type": "string"},
            "minio_awake_duration": number_type,
            "heartbeat_interval": number_type,
            "heartbeat_miss_tolerance": number_type,
            "heartbeat_timeout": number_type,
            "minio_start_timeout": number_type,
            "minio_setup_timeout": number_type,
            "minio_stop_timeout": number_type,
        },
        "required": [
            "port_min",
            "port_max",
            "sudo",
            "minio_awake_duration",
            "heartbeat_interval",
            "heartbeat_miss_tolerance",
            "heartbeat_timeout",
            "minio_start_timeout",
            "minio_setup_timeout",
            "minio_stop_timeout",
        ],
        "additionalProperties": False,
    }
    minio = {
        "type": "object",
        "properties": {
            "minio": {"type": "string"},
            "mc": {"type": "string"},
        },
        "required": [
            "minio",
            "mc",
        ],
        "additionalProperties": False,
    }
    sc = {
        "type": "object",
        "properties": {
            "redis": redis_schema(number_type),
            "gunicorn": gunicorn_schema(number_type),
            "aws_signature": {"type": "string"},
            "multiplexer": multiplexer,
            "minio_manager": minio_manager,
            "minio": minio,
            "log_file": {"type": "string"},
            "log_syslog": syslog_schema(),
        },
        "required": [
            "redis",
            "gunicorn",
            "multiplexer",
            "minio_manager",
            "minio",
            "log_syslog",
        ],
        "additionalProperties": False,
    }
    return sc


def adm_schema(number_type):
    multiplexer = {
        "type": "object",
        "properties": {
            "facade_hostname": {"type": "string"},
            "probe_access_timeout": number_type,
        },
        "required": [
            "facade_hostname",
            "probe_access_timeout",
        ],
        "additionalProperties": False,
    }
    minio_manager = {"type": "string"}
    ##{
    ##    "type": "object",
    ##    "properties": {
    ##    },
    ##    "required": [
    ##    ],
    ##    "additionalProperties": False,
    ##}
    minio = {
        "type": "object",
        "properties": {
            "minio": {"type": "string"},
            "mc": {"type": "string"},
        },
        "required": [
            "minio",
            "mc",
        ],
        "additionalProperties": False,
    }
    system = {
        "type": "object",
        "properties": {
            "max_pool_expiry": number_type,
        },
        "required": [
            "max_pool_expiry",
        ],
        "additionalProperties": False,
    }
    webui = {
        "type": "object",
        "properties": {
            "trusted_proxies": {"type": "array", "items": {"type": "string"}},
            "CSRF_secret_key": {"type": "string"},
        },
        "required": [
            "trusted_proxies",
            "CSRF_secret_key",
        ],
        "additionalProperties": False,
    }
    sc = {
        "type": "object",
        "properties": {
            "gunicorn": gunicorn_schema(number_type),
            "redis": redis_schema(number_type),
            "aws_signature": {"type": "string"},
            "multiplexer": multiplexer,
            "minio_manager": minio_manager,
            "system": system,
            "webui": webui,
            "minio": minio,
            "log_file": {"type": "string"},
            "log_syslog": syslog_schema(),
        },
        "required": [
            "gunicorn",
            "redis",
            "multiplexer",
            #"minio_manager",
            "system",
            "webui",
            "minio",
            "log_syslog",
        ],
        "additionalProperties": False,
    }
    return sc


def validate_mux_conf(conf):
    jsonschema.validate(instance=conf, schema=mux_schema({"type": "string"}))
    check_type_number(conf, mux_schema({"type": "number"}))
    pass


def validate_adm_conf(conf):
    jsonschema.validate(instance=conf, schema=adm_schema({"type": "string"}))
    check_type_number(conf, adm_schema({"type": "number"}))
    pass


def check_type_number(conf, schema):
    if schema["type"] == "object":
        for (prop, sub_schema) in schema["properties"].items():
            val = conf.get(prop)
            if val:
                check_type_number(val, sub_schema)
            elif prop in schema["required"]:
                raise Exception(f"missing required {prop}")
            pass
    elif schema["type"] == "array":
        sub_schema = schema["items"]
        if not isinstance(conf, list):
            raise Exception(f"not an array: {conf}")
        for e in conf:
            check_type_number(e, sub_schema)
            pass
    elif schema["type"] == "string":
        if not isinstance(conf, str):
            raise Exception(f"not a string: {conf}")
        pass
    elif schema["type"] == "number":
        if not isinstance(conf, str) or not conf.isdigit():
            raise Exception(f"not a number: {conf}")
        pass
    else:
        raise Exception("INTERNAL ERROR: NOT IMPLEMENTED")
    pass


def fix_adm_conf(conf):
    return conf


def fix_mux_conf(conf):
    return conf
