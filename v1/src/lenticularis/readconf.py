"""A config file reader.  Config files are in yaml, and they are read
and checked against json schema."""

# Copyright (c) 2022 RIKEN R-CCS
# SPDX-License-Identifier: BSD-2-Clause

import os
import sys
import jsonschema
import yaml
from lenticularis.utility import rephrase_exception_message


_mux_conf_env_name = "LENS3_MUX_CONFIG"
_api_conf_env_name = "LENS3_API_CONFIG"


def read_mux_conf(configfile=None):
    return readconf(configfile, _fix_mux_conf, _validate_mux_conf,
                    _mux_conf_env_name)


def read_api_conf(configfile=None):
    return readconf(configfile, _fix_api_conf, _validate_api_conf,
                    _api_conf_env_name)


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


def _gunicorn_schema():
    _schema = {
        "type": "object",
        "properties": {
            "port": {"type": "string"},
            "workers": {"type": "number"},
            "threads": {"type": "number"},
            "timeout": {"type": "number"},
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
    return _schema


def _redis_schema():
    _schema = {
        "type": "object",
        "properties": {
            "host": {"type": "string"},
            "port": {"type": "number"},
            "password": {"type": "string"},
        },
        "required": [
            "host",
            "port",
            "password",
        ],
        "additionalProperties": False,
    }
    return _schema


def _syslog_schema():
    _schema = {
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
    return _schema


def _mux_schema():
    multiplexer = {
        "type": "object",
        "properties": {
            "front_host": {"type": "string"},
            "trusted_proxies": {"type": "array", "items": {"type": "string"}},
            "mux_ep_update_interval": {"type": "number"},
            "forwarding_timeout": {"type": "number"},
            "probe_access_timeout": {"type": "number"},
            "bad_response_delay": {"type": "number"},
        },
        "required": [
            "front_host",
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
            "port_min": {"type": "number"},
            "port_max": {"type": "number"},
            "minio_awake_duration": {"type": "number"},
            "minio_setup_at_restart": {"type": "boolean"},
            "heartbeat_interval": {"type": "number"},
            "heartbeat_miss_tolerance": {"type": "number"},
            "heartbeat_timeout": {"type": "number"},
            "minio_start_timeout": {"type": "number"},
            "minio_setup_timeout": {"type": "number"},
            "minio_stop_timeout": {"type": "number"},
            "minio_mc_timeout": {"type": "number"},
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
    _schema = {
        "type": "object",
        "properties": {
            "version": {"type": "string"},
            "aws_signature": {"type": "string"},
            "redis": _redis_schema(),
            "gunicorn": _gunicorn_schema(),
            "multiplexer": multiplexer,
            "minio_manager": minio_manager,
            "minio": minio,
            "log_file": {"type": "string"},
            "log_syslog": _syslog_schema(),
        },
        "required": [
            "version",
            "aws_signature",
            "redis",
            "gunicorn",
            "multiplexer",
            "minio_manager",
            "minio",
            "log_syslog",
        ],
        "additionalProperties": False,
    }
    return _schema


def _api_schema():
    controller = {
        "type": "object",
        "properties": {
            "front_host": {"type": "string"},
            "trusted_proxies": {"type": "array", "items": {"type": "string"}},
            "base_path": {"type": "string"},
            "claim_to_uid": {"type": "string"},
            "probe_access_timeout": {"type": "number"},
            "minio_mc_timeout": {"type": "number"},
            "max_pool_expiry": {"type": "number"},
            "CSRF_secret_key": {"type": "string"},
        },
        "required": [
            "front_host",
            "trusted_proxies",
            "base_path",
            "claim_to_uid",
            "probe_access_timeout",
            "max_pool_expiry",
            "CSRF_secret_key",
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
    _schema = {
        "type": "object",
        "properties": {
            "version": {"type": "string"},
            "aws_signature": {"type": "string"},
            "redis": _redis_schema(),
            "gunicorn": _gunicorn_schema(),
            "controller": controller,
            "minio": minio,
            "log_file": {"type": "string"},
            "log_syslog": _syslog_schema(),
        },
        "required": [
            "version",
            "aws_signature",
            "redis",
            "gunicorn",
            "controller",
            "minio",
            "log_syslog",
        ],
        "additionalProperties": False,
    }
    return _schema


def _validate_mux_conf(conf):
    jsonschema.validate(instance=conf, schema=_mux_schema())
    pass


def _validate_api_conf(conf):
    jsonschema.validate(instance=conf, schema=_api_schema())
    claim = conf["controller"]["claim_to_uid"]
    keyset = {"uid", "email-id"}
    if not claim in keyset:
        raise Exception(f"api-config: bad claim_to_uid={claim};"
                        f" it should be one of {keyset}")
    pass


def _fix_type(data, schema):
    """Rereads and fixes tokens in yaml to match for json schema.  It
    passes missing/additional properties, which are checked by json
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
    schema = _mux_schema()
    conf = _fix_type(conf, schema)
    return conf


def _fix_api_conf(conf):
    schema = _api_schema()
    conf = _fix_type(conf, schema)
    return conf
