"""A config file reader."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
import sys
import jsonschema
import yaml
from lenticularis.utility import rephrase_exception_message


_mux_conf_envname = "LENTICULARIS_MUX_CONFIG"
_wui_conf_envname = "LENTICULARIS_WUI_CONFIG"


def read_mux_conf(configfile=None):
    return readconf(configfile, _fix_mux_conf, _validate_mux_conf,
                    _mux_conf_envname)


def read_wui_conf(configfile=None):
    return readconf(configfile, _fix_wui_conf, _validate_wui_conf,
                    _wui_conf_envname)


def readconf(configfile, fixfn, valfn, envname):
    if configfile is None:
        configfile = os.environ.get(envname)
        pass
    assert configfile is not None
    try:
        with open(configfile, "r") as f:
            yamlconf = yaml.load(f, Loader=yaml.BaseLoader)
    except yaml.YAMLError as e:
        raise Exception(f"Reading a config file failed: {configfile}:"
                        f" exception=({e})")
    except Exception as e:
        m = rephrase_exception_message(e)
        raise Exception(f"Reading a config file failed: {configfile}:"
                        f" exception=({m})")
    conf = fixfn(yamlconf)
    valfn(conf)
    return (conf, configfile)


def _gunicorn_schema(number_type):
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


def _redis_schema(number_type):
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


def _syslog_schema(number_type):
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


def _mux_schema(number_type):
    multiplexer = {
        "type": "object",
        "properties": {
            "facade_hostname": {"type": "string"},
            "trusted_proxies": {"type": "array", "items": {"type": "string"}},
            "mux_ep_update_interval": number_type,
            "forwarding_timeout": number_type,
            "probe_access_timeout": number_type,
            "bad_response_delay": number_type,
        },
        "required": [
            "facade_hostname",
            "trusted_proxies",
            "mux_ep_update_interval",
            "forwarding_timeout",
            "probe_access_timeout",
            "bad_response_delay",
        ],
        "additionalProperties": False,
    }
    minio_manager = {
        "type": "object",
        "properties": {
            "sudo": {"type": "string"},
            "port_min": number_type,
            "port_max": number_type,
            "minio_awake_duration": number_type,
            "minio_setup_at_restart": {"type": "boolean"},
            "heartbeat_interval": number_type,
            "heartbeat_miss_tolerance": number_type,
            "heartbeat_timeout": number_type,
            "minio_start_timeout": number_type,
            "minio_setup_timeout": number_type,
            "minio_stop_timeout": number_type,
            "minio_mc_timeout": number_type,
        },
        "required": [
            "sudo",
            "port_min",
            "port_max",
            "minio_awake_duration",
            "minio_setup_at_restart",
            "heartbeat_interval",
            "heartbeat_miss_tolerance",
            "heartbeat_timeout",
            "minio_start_timeout",
            "minio_setup_timeout",
            "minio_stop_timeout",
            "minio_mc_timeout",
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
            "redis": _redis_schema(number_type),
            "gunicorn": _gunicorn_schema(number_type),
            "aws_signature": {"type": "string"},
            "multiplexer": multiplexer,
            "minio_manager": minio_manager,
            "minio": minio,
            "log_file": {"type": "string"},
            "log_syslog": _syslog_schema(number_type),
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


def _wui_schema(number_type):
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
    minio_manager = {
        "type": "object",
        "properties": {
            "minio_mc_timeout": number_type,
        },
        "required": [
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
    system = {
        "type": "object",
        "properties": {
            "trusted_proxies": {"type": "array", "items": {"type": "string"}},
            "max_pool_expiry": number_type,
            "CSRF_secret_key": {"type": "string"},
        },
        "required": [
            "trusted_proxies",
            "max_pool_expiry",
            "CSRF_secret_key",
        ],
        "additionalProperties": False,
    }
    sc = {
        "type": "object",
        "properties": {
            "redis": _redis_schema(number_type),
            "gunicorn": _gunicorn_schema(number_type),
            "aws_signature": {"type": "string"},
            "multiplexer": multiplexer,
            "minio_manager": minio_manager,
            "minio": minio,
            "system": system,
            "log_file": {"type": "string"},
            "log_syslog": _syslog_schema(number_type),
        },
        "required": [
            "gunicorn",
            "redis",
            "multiplexer",
            "minio_manager",
            "minio",
            "system",
            "log_syslog",
        ],
        "additionalProperties": False,
    }
    return sc


def _validate_mux_conf(conf):
    jsonschema.validate(instance=conf, schema=_mux_schema({"type": "number"}))
    pass


def _validate_wui_conf(conf):
    jsonschema.validate(instance=conf, schema=_wui_schema({"type": "number"}))
    pass


def _fix_type(data, schema):
    """Rereads tokens as for schema.  It fixes yaml data.  It passes
    missing/additional properties, which are checked by json
    validation.
    """
    if schema["type"] == "object":
        newdata = data.copy()
        for (prop, subschema) in schema["properties"].items():
            subdata = data.get(prop)
            # assert prop not in schema["required"] or subdata is not None
            if subdata is not None:
                newdata[prop] = _fix_type(subdata, subschema)
                pass
            pass
        return newdata
    elif schema["type"] == "array":
        subschema = schema["items"]
        assert isinstance(data, list)
        return [_fix_type(subdata, subschema) for subdata in data]
    elif schema["type"] == "string":
        assert isinstance(data, str)
        return data
    elif schema["type"] == "number":
        assert isinstance(data, str)
        try:
            return int(data)
        except ValueError:
            return float(data)
    elif schema["type"] == "boolean":
        assert isinstance(data, str)
        return bool(data)
    else:
        raise Exception("_fix_type: Other types are not implemented")
    pass


def _fix_mux_conf(conf):
    schema = _mux_schema({"type": "number"})
    conf = _fix_type(conf, schema)
    return conf


def _fix_wui_conf(conf):
    schema = _wui_schema({"type": "number"})
    conf = _fix_type(conf, schema)
    return conf
