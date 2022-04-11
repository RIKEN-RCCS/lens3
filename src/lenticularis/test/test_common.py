# Copyright (c) 2022 RIKEN R-CCS.
# SPDX-License-Identifier: BSD-2-Clause

from lenticularis.utility import logger, openlog
from lenticularis.utility import encrypt_secret
from lenticularis.utility import decrypt_secret
from lenticularis.utility import rot13
from lenticularis.utility import random_str
from lenticularis.utility import forge_s3_auth
from lenticularis.utility import parse_s3_auth
from lenticularis.utility import check_mux_access
from lenticularis.utility import check_permission
from lenticularis.utility import make_clean_env
#from lenticularis.utility import validate_zone_dict
#from lenticularis.utility import semantic_check_zone_dict
from lenticularis.utility import outer_join
from lenticularis.utility import format_rfc3339_z
from lenticularis.utility import sha1
from lenticularis.utility import remove_trailing_shash
from lenticularis.utility import pick_one
from lenticularis.utility import dict_diff
#from lenticularis.utility import gen_access_key_id, gen_secret_access_key, test_gen_mc_alias
import sys

#def test_gen_access_key_id():
#    pass

#def test_gen_secret_access_key():
#    pass

#def test_gen_mc_alias():
#    pass

#def test_openlog():
#    pass


#class test_Read1Reader():
#    pass


def test_encrypt_secret():
    input = ("abcdefghijklmnopqrstuvwxyz"
             "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
             "0123456789"
             " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
             )
    expected = ("$13$nopqrstuvwxyzabcdefghijklm"
             "NOPQRSTUVWXYZABCDEFGHIJKLM"
             "0123456789"
             " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
             )
    got = encrypt_secret(input)
    assert got == expected


def test_decrypt_secret():
    input = ("$13$abcdefghijklmnopqrstuvwxyz"
             "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
             "0123456789"
             " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
             )
    expected = ("nopqrstuvwxyzabcdefghijklm"
             "NOPQRSTUVWXYZABCDEFGHIJKLM"
             "0123456789"
             " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
             )
    got = decrypt_secret(input)
    assert got == expected


def test_rot13():
    input = ("abcdefghijklmnopqrstuvwxyz"
             "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
             "0123456789"
             " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
             )
    expected = ("nopqrstuvwxyzabcdefghijklm"
             "NOPQRSTUVWXYZABCDEFGHIJKLM"
             "0123456789"
             " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
             )
    got = rot13(input)
    assert got == expected


def test_random_str():
    for input in [1, 2, 4, 8, 16, 32, 64]:
        got = random_str(input)
        assert len(got) == input
        assert got[0].isalpha()
        assert got.isalnum()


def test_forge_s3_auth():
    input = "K4XcKzocrUhrnCAKrx2Z"
    expected = input
    got = parse_s3_auth(forge_s3_auth(input))
    assert got == expected


def test_parse_s3_auth():
    input = "AWS4-HMAC-SHA256 Credential=K4XcKzocrUhrnCAKrx2Z/20210827//s3/aws4_request, SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature=964e588cbc741925fa98c576ca7cc5fdd5b44e92c3e8996b81f18b48abeb6804"
    expected = "K4XcKzocrUhrnCAKrx2Z"
    got = parse_s3_auth(input)
    assert got == expected


def test_send_decoy_packet():
    input = None
    expected = None
    got = None
    assert got == expected


def test_check_permission():
    openlog()
    for item in [((None, [["allow", "user1"]]), "denied"),
                 ((None, [["allow", "*"]]), "denied"),
                 ((None, []), "denied"),
                 (("u", []), "allowed"),
                 (("u", [["allow", "*"]]), "allowed"),
                 (("u", [["deny", "*"]]), "denied"),
                 (("user2", [["deny", "user2"]]), "denied"),
                 (("user2", [["allow", "user2"], ["deny", "user2"]]), "allowed"),
                 (("user2", [["deny", "user2"], ["allow", "user2"]]), "denied"),
                 (("user3", [["deny", "user2"]]), "allowed"),
                 (("user3", [["allow", "user1"], ["deny", "user2"]]), "allowed"),
                 (("user2", [["deny", "user2"], ["allow", "*"]]), "denied"),
                 (("user2", [["deny", "user3"], ["allow", "*"]]), "allowed"),
                 (("user2", [["deny", "user2"], ["deny", "*"]]), "denied"),
                 (("user2", [["deny", "user3"], ["deny", "*"]]), "denied"),
                 (("user2", [["allow", "user2"], ["deny", "*"]]), "allowed"),
                 (("user2", [["allow", "user3"], ["deny", "*"]]), "denied"),
                 (("user1", [["allow", "user1"]]), "allowed")]:
        (input, expected) = item
        user = input[0]
        rules = input[1]
        got = check_permission(user, rules)
        logger.info(f"@@@ user = {user}  rules = {rules}  got = {got}  expected = {expected}")
        assert got == expected


def test_make_clean_env():
    input = {
"XAPPLRESDIR": "/lib/app-defaults/",
"SSH_CONNECTION": "22.22.22.22 36154 22.22.22.23 22",
"MAILCHECK": "120",
"LANG": "C",
"LESS": "-CMLXfan",
"PYENV_ROOT": "/opt/pyenv",
"EDITOR": "vi",
"PYENV_HOOK_PATH": "/home/test/opt/pyenv/pyenv.d:...",
"CVSROOT": "cvs@cvs:/cvsroot",
"SSH_AUTH_SOCK": "/tmp/ssh-vGz9A136Tk/agent.434",
"XDG_SESSION_ID": "10",
"USER": "test",
"PYENV_DIR": "/home/test/work/object-storage/src/lenticularis/test",
"PWD": "/home/test/work/object-storage/src/lenticularis/test",
"FCEDIT": "/home/test/bin/vi",
"HOME": "/home/test",
"MAILPATH": "/var/mail/test?You have mail:/var/mail/root?Root has mail",
"LESSHISTFILE": "-",
"LC_CTYPE": "en_US.UTF-8",
"HOST": "Se",
"SSH_CLIENT": "10.22.22.22 36154 22",
"PYENV_VERSION": "lenticularis",
"XDG_DATA_DIRS": "/usr/local/share:/usr/share:/var/lib/snapd/desktop",
"HISTFILE": "/home/test/.sh_history/0",
"A__z": "\"*MAILCHECK=\"*SHLVL",
"TMPDIR": "/tmp",
"SSH_TTY": "/dev/pts/0",
"MAIL": "/var/mail/test",
"TERM": "vt100",
"SHELL": "/bin/sh",
"SHLVL": "1",
"PYENV_SHELL": "ksh",
"MANPATH": "/usr/man:/usr/share/man:/usr/local/man",
"BLOCKSIZE": "1024",
"LESSCHARSET": "utf-8",
"LOGNAME": "test",
"XDG_RUNTIME_DIR": "/run/user/230",
"PATH": "/opt/pyenv/versions/lenticularis/bin:/opt/pyenv/libexec:/opt/pyenv/plugins/python-build/bin:/opt/pyenv/plugins/pyenv-virtualenv/bin:/opt/pyenv/plugins/pyenv-update/bin:/opt/pyenv/plugins/pyenv-installer/bin:/opt/pyenv/plugins/pyenv-doctor/bin:/opt/pyenv/shims:/opt/pyenv/bin:/home/test/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
"CVS_RSH": "ssh"}

    expected = {"LANG": "C",
"USER": "test",
"HOME": "/home/test",
"LC_CTYPE": "en_US.UTF-8",
"SHELL": "/bin/sh",
"LOGNAME": "test",
"PATH": "/opt/pyenv/versions/lenticularis/bin:/opt/pyenv/libexec:/opt/pyenv/plugins/python-build/bin:/opt/pyenv/plugins/pyenv-virtualenv/bin:/opt/pyenv/plugins/pyenv-update/bin:/opt/pyenv/plugins/pyenv-installer/bin:/opt/pyenv/plugins/pyenv-doctor/bin:/opt/pyenv/shims:/opt/pyenv/bin:/home/test/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"}

    got = make_clean_env(input)
    assert got == expected


#def test_zone_schema():
#    pass


def test_validate_zone_dict():
    input = None
    expected = None
    got = None
    assert got == expected


def test_semantic_check_zone_dict():
    input = None
    expected = None
    got = None
    assert got == expected


def test_outer_join():
    got = []

    left = [{"Key": "k3", "val": 3},
            {"Key": "k2", "val": 2},
            {"Key": "k5", "val": 5},
            {"Key": "k1", "val": 1},
            {"Key": "k0", "val": 0},
            {"Key": "k0", "val": 0},
            ]
    def lkey(e):
        return e.get("Key")
    def lval(e):
        return e.get("val")

    right = [{"ky": "k4", "VAL": 40},
            {"ky": "k2", "VAL": 20},
            {"ky": "k0", "VAL": 0},
            {"ky": "k5", "VAL": 50},
            {"ky": "k5", "VAL": 50},
            {"ky": "k1", "VAL": 10},
            ]
    def rkey(e):
        return e.get("ky")
    def rval(e):
        return e.get("VAL")

    def fn(le, ri):
        if le == None:
            r = (None, rval(ri))
        elif ri == None:
            r = (lval(le), None)
        else:
            r = (lval(le), rval(ri))
        got.append(r)

    expected = [(0, 0),
                (0, None),
                (1, 10),
                (2, 20),
                (3, None),
                (None, 40),
                (5, 50),
                (None, 50),
                ]

    outer_join(left, lkey, right, rkey, fn)
    assert got == expected


def test_remove_trailing_shash():
    for item in [("work/", "work"),
                 ("work", "work")]:
        (input, expected) = item
        got = remove_trailing_shash(input)
        assert got == expected


def test_sha1():
    for item in [(b"", "da39a3ee5e6b4b0d3255bfef95601890afd80709"),
                 (b"abc", "a9993e364706816aba3e25717850c26c9cd0d89d")]:
        (input, expected) = item
        got = sha1(input)
        assert got == expected


def test_format_rfc3339_z():
    for item in [(0, "1970-01-01T00:00:00.000000Z"),
                 (1635212507, "2021-10-26T01:41:47.000000Z")]:
        (input, expected) = item
        got = format_rfc3339_z(input)
        assert got == expected


def test_pick_one():
    for item in [[],
                 ["1"],
                 ["1", "2", "3"],
                 ["1", "2", "3", "4", "5"]]:
        input = item
        got = pick_one(input)
        if input == []:
            assert got is None
        else:
            assert got in input


def test_dict_diff():
    for item in [(({}, {}),
                  []
                 ),
                 (({"key": "val"}, {"key": "val"}),
                  []
                 ),
                 (({"key": "val"}, {"key": "val1"}),
                  [{"reason": "value changed", "key": "key", "existing": "val", "new": "val1"}]
                 ),
                 (({"key": "val"}, {"key2": "val"}),
                  [{"reason": "key deleted", "existing": "key"},
                   {"reason": "key appeared", "new": "key2"}]
                 ),
                 (({}, {"key2": "val"}),
                  [{"reason": "key appeared", "new": "key2"}]
                 ),
                 (({"key": "val"}, {}),
                  [{"reason": "key deleted", "existing": "key"}]
                 ),
                 (({"key": "val", "key2": "val2"}, {"key": "val4", "key3": "val2"}),
                  [{"reason": "value changed", "key": "key", "existing": "val", "new": "val4"},
                   {"reason": "key deleted", "existing": "key2"},
                   {"reason": "key appeared", "new": "key3"}]
                 ),
                ]:
        (input, expected) = item
        got = dict_diff(input[0], input[1])
        for e in expected:
            assert e in got
        for g in got:
            assert g in expected
